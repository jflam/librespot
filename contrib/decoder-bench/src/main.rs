use librespot_playback::decoder::{AudioDecoder, SymphoniaDecoder};
use std::{
    error::Error,
    fs::{self, File},
    hint::black_box,
    io::{BufWriter, Cursor, Write},
    sync::Arc,
    time::Instant,
};
use symphonia::core::probe::Hint;

type Result<T> = std::result::Result<T, Box<dyn Error>>;

fn decoder(data: Arc<[u8]>) -> Result<SymphoniaDecoder> {
    let mut hint = Hint::new();
    hint.with_extension("ogg");
    Ok(SymphoniaDecoder::new(Cursor::new(data), hint)?)
}

fn consume(decoder: &mut SymphoniaDecoder) -> Result<(usize, usize)> {
    let (mut samples, mut packets) = (0, 0);
    while let Some((_, packet)) = decoder.next_packet()? {
        samples += packet.samples()?.len();
        packets += 1;
        black_box(&packet);
    }
    Ok((samples, packets))
}

fn cpu_seconds() -> Result<f64> {
    let mut value = libc::timespec {
        tv_sec: 0,
        tv_nsec: 0,
    };
    // Process CPU time includes every thread, user and system time. No device
    // or privileged tracing access is involved.
    if unsafe { libc::clock_gettime(libc::CLOCK_PROCESS_CPUTIME_ID, &mut value) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    Ok(value.tv_sec as f64 + value.tv_nsec as f64 / 1e9)
}

fn dump(decoder: &mut SymphoniaDecoder, prefix: &str) -> Result<()> {
    let mut pcm = BufWriter::new(File::create(format!("{prefix}.f64le"))?);
    let mut positions = BufWriter::new(File::create(format!("{prefix}.tsv"))?);
    while let Some((position, packet)) = decoder.next_packet()? {
        let samples = packet.samples()?;
        writeln!(
            positions,
            "{}\t{}\t{}",
            position.position_ms,
            samples.len(),
            position.skipped
        )?;
        for sample in samples {
            if !sample.is_finite() {
                return Err("non-finite PCM".into());
            }
            pcm.write_all(&sample.to_le_bytes())?;
        }
    }
    pcm.flush()?;
    positions.flush()?;
    Ok(())
}

fn main() -> Result<()> {
    let args: Vec<_> = std::env::args().collect();
    if args.len() != 5 {
        return Err("usage: decoder-bench bench FIXTURE PASSES LABEL | decoder-bench dump FIXTURE PREFIX LABEL".into());
    }
    let data: Arc<[u8]> = fs::read(&args[2])?.into();
    match args[1].as_str() {
        "bench" => {
            let passes: usize = args[3].parse()?;
            if passes == 0 {
                return Err("passes must be positive".into());
            }
            let expected = consume(&mut decoder(data.clone())?)?;
            if expected.0 == 0 || expected.0 % 2 != 0 {
                return Err("invalid stereo sample count".into());
            }
            consume(&mut decoder(data.clone())?)?;
            let started = Instant::now();
            let cpu_started = cpu_seconds()?;
            for _ in 0..passes {
                let actual = consume(&mut decoder(data.clone())?)?;
                if actual != expected {
                    return Err("decode count changed between passes".into());
                }
            }
            let cpu = cpu_seconds()? - cpu_started;
            let wall = started.elapsed().as_secs_f64();
            let audio = expected.0 as f64 / 88200.0 * passes as f64;
            println!(
                "{{\"label\":\"{}\",\"simd\":{},\"passes\":{},\"samples_per_pass\":{},\"packets_per_pass\":{},\"audio_seconds\":{:.9},\"cpu_seconds\":{:.9},\"wall_seconds\":{:.9},\"realtime_cpu_percent\":{:.9}}}",
                args[4],
                cfg!(feature = "simd"),
                passes,
                expected.0,
                expected.1,
                audio,
                cpu,
                wall,
                cpu / audio * 100.0
            );
        }
        "dump" => {
            let mut decoded = decoder(data)?;
            dump(&mut decoded, &format!("{}.full", args[3]))?;
            let actual_seek = decoded.seek(5731)?;
            dump(&mut decoded, &format!("{}.seek", args[3]))?;
            println!(
                "{{\"label\":\"{}\",\"seek_requested_ms\":5731,\"seek_returned_ms\":{actual_seek}}}",
                args[4]
            );
        }
        _ => return Err("unknown command".into()),
    }
    Ok(())
}
