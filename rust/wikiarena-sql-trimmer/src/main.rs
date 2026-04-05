use std::env;
use std::fs;
use std::io::{self, BufReader, BufWriter, Write};
use std::path::PathBuf;

use wikiarena_sql_trimmer::{trim_reader_to_writer, TrimKind};

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}

fn run() -> Result<(), String> {
    let mut args = env::args().skip(1);
    let mut kind = None;
    let mut stats_path = None;

    while let Some(argument) = args.next() {
        match argument.as_str() {
            "--kind" => {
                let value = args
                    .next()
                    .ok_or_else(|| "missing value for --kind".to_string())?;
                kind = TrimKind::from_cli_value(&value);
                if kind.is_none() {
                    return Err(format!("unsupported --kind value: {value}"));
                }
            }
            "--stats-path" => {
                let value = args
                    .next()
                    .ok_or_else(|| "missing value for --stats-path".to_string())?;
                stats_path = Some(PathBuf::from(value));
            }
            "--help" | "-h" => {
                print_usage();
                return Ok(());
            }
            _ => return Err(format!("unsupported argument: {argument}")),
        }
    }

    let kind = kind.ok_or_else(|| "--kind is required".to_string())?;
    let stats_path = stats_path.ok_or_else(|| "--stats-path is required".to_string())?;

    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut reader = BufReader::with_capacity(8 * 1024 * 1024, stdin.lock());
    let mut writer = BufWriter::with_capacity(8 * 1024 * 1024, stdout.lock());
    let stats =
        trim_reader_to_writer(kind, &mut reader, &mut writer).map_err(|error| error.to_string())?;
    writer
        .flush()
        .map_err(|error| format!("failed to flush output: {error}"))?;

    fs::write(
        stats_path,
        format!(
            "{{\"processed_lines\":{},\"written_rows\":{}}}",
            stats.processed_lines, stats.written_rows,
        ),
    )
    .map_err(|error| format!("failed to write stats file: {error}"))?;

    Ok(())
}

fn print_usage() {
    eprintln!(
        "Usage: wikiarena-sql-trimmer --kind <pages|links|redirects|targets> --stats-path <path>"
    );
}
