use std::error::Error;
use std::fmt::{Display, Formatter};
use std::io::{BufRead, Write};

const PAGE_INSERT_PREFIX: &[u8] = b"INSERT INTO `page` VALUES ";
const PAGELINKS_INSERT_PREFIX: &[u8] = b"INSERT INTO `pagelinks` VALUES ";
const REDIRECT_INSERT_PREFIX: &[u8] = b"INSERT INTO `redirect` VALUES ";
const LINKTARGET_INSERT_PREFIX: &[u8] = b"INSERT INTO `linktarget` VALUES ";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TrimKind {
    Pages,
    Links,
    Redirects,
    Targets,
}

impl TrimKind {
    pub fn from_cli_value(value: &str) -> Option<Self> {
        match value {
            "pages" => Some(Self::Pages),
            "links" => Some(Self::Links),
            "redirects" => Some(Self::Redirects),
            "targets" => Some(Self::Targets),
            _ => None,
        }
    }

    fn insert_prefix(self) -> &'static [u8] {
        match self {
            Self::Pages => PAGE_INSERT_PREFIX,
            Self::Links => PAGELINKS_INSERT_PREFIX,
            Self::Redirects => REDIRECT_INSERT_PREFIX,
            Self::Targets => LINKTARGET_INSERT_PREFIX,
        }
    }
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub struct TrimStats {
    pub processed_lines: u64,
    pub written_rows: u64,
}

#[derive(Debug, Clone, Eq, PartialEq)]
pub struct TrimError {
    message: String,
}

impl TrimError {
    fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl Display for TrimError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl Error for TrimError {}

pub fn trim_reader_to_writer<R: BufRead, W: Write>(
    kind: TrimKind,
    reader: &mut R,
    writer: &mut W,
) -> Result<TrimStats, TrimError> {
    let mut stats = TrimStats::default();
    let mut line_buffer = Vec::with_capacity(1024 * 1024);
    let mut row_buffer = Vec::with_capacity(512);

    loop {
        line_buffer.clear();
        let bytes_read = reader
            .read_until(b'\n', &mut line_buffer)
            .map_err(|error| TrimError::new(format!("failed to read input: {error}")))?;
        if bytes_read == 0 {
            break;
        }

        stats.processed_lines += 1;
        stats.written_rows += trim_insert_line(
            kind,
            stats.processed_lines,
            &line_buffer,
            writer,
            &mut row_buffer,
        )?;
    }

    Ok(stats)
}

fn trim_insert_line<W: Write>(
    kind: TrimKind,
    line_number: u64,
    raw_line: &[u8],
    writer: &mut W,
    row_buffer: &mut Vec<u8>,
) -> Result<u64, TrimError> {
    let line = strip_trailing_line_endings(raw_line);
    let insert_prefix = kind.insert_prefix();
    if !line.starts_with(insert_prefix) {
        return Ok(0);
    }
    if line.len() <= insert_prefix.len() || line[line.len() - 1] != b';' {
        return Err(trim_error(
            line_number,
            0,
            "expected INSERT line to end with ';'",
        ));
    }

    let line_end_index = line.len() - 1;
    let mut index = insert_prefix.len();
    let mut written_rows = 0_u64;

    while index < line_end_index {
        skip_tuple_separators(line, &mut index, line_end_index);
        if index >= line_end_index {
            break;
        }

        expect_byte(line, &mut index, line_end_index, b'(', line_number)?;
        match kind {
            TrimKind::Pages => write_page_row(
                line,
                &mut index,
                line_end_index,
                line_number,
                writer,
                row_buffer,
            )?,
            TrimKind::Links => write_pagelinks_row(
                line,
                &mut index,
                line_end_index,
                line_number,
                writer,
                row_buffer,
            )?,
            TrimKind::Redirects => write_redirect_row(
                line,
                &mut index,
                line_end_index,
                line_number,
                writer,
                row_buffer,
            )?,
            TrimKind::Targets => write_linktarget_row(
                line,
                &mut index,
                line_end_index,
                line_number,
                writer,
                row_buffer,
            )?,
        }
        written_rows += 1;
    }

    Ok(written_rows)
}

fn write_page_row<W: Write>(
    input: &[u8],
    index: &mut usize,
    line_end_index: usize,
    line_number: u64,
    writer: &mut W,
    row_buffer: &mut Vec<u8>,
) -> Result<(), TrimError> {
    row_buffer.clear();
    append_unquoted_field(row_buffer, input, index, line_end_index, line_number)?;
    expect_comma(input, index, line_end_index, line_number)?;
    append_unquoted_field(row_buffer, input, index, line_end_index, line_number)?;
    expect_comma(input, index, line_end_index, line_number)?;
    append_quoted_field(row_buffer, input, index, line_end_index, line_number)?;
    expect_comma(input, index, line_end_index, line_number)?;
    append_unquoted_field(row_buffer, input, index, line_end_index, line_number)?;
    finish_tuple(input, index, line_end_index, line_number)?;
    write_row(writer, row_buffer, line_number)
}

fn write_pagelinks_row<W: Write>(
    input: &[u8],
    index: &mut usize,
    line_end_index: usize,
    line_number: u64,
    writer: &mut W,
    row_buffer: &mut Vec<u8>,
) -> Result<(), TrimError> {
    row_buffer.clear();
    append_unquoted_field(row_buffer, input, index, line_end_index, line_number)?;
    expect_comma(input, index, line_end_index, line_number)?;
    append_unquoted_field(row_buffer, input, index, line_end_index, line_number)?;
    expect_comma(input, index, line_end_index, line_number)?;
    append_unquoted_field(row_buffer, input, index, line_end_index, line_number)?;
    finish_tuple(input, index, line_end_index, line_number)?;
    write_row(writer, row_buffer, line_number)
}

fn write_redirect_row<W: Write>(
    input: &[u8],
    index: &mut usize,
    line_end_index: usize,
    line_number: u64,
    writer: &mut W,
    row_buffer: &mut Vec<u8>,
) -> Result<(), TrimError> {
    row_buffer.clear();
    append_unquoted_field(row_buffer, input, index, line_end_index, line_number)?;
    expect_comma(input, index, line_end_index, line_number)?;
    append_unquoted_field(row_buffer, input, index, line_end_index, line_number)?;
    expect_comma(input, index, line_end_index, line_number)?;
    append_quoted_field(row_buffer, input, index, line_end_index, line_number)?;
    finish_tuple(input, index, line_end_index, line_number)?;
    write_row(writer, row_buffer, line_number)
}

fn write_linktarget_row<W: Write>(
    input: &[u8],
    index: &mut usize,
    line_end_index: usize,
    line_number: u64,
    writer: &mut W,
    row_buffer: &mut Vec<u8>,
) -> Result<(), TrimError> {
    row_buffer.clear();
    append_unquoted_field(row_buffer, input, index, line_end_index, line_number)?;
    expect_comma(input, index, line_end_index, line_number)?;
    append_unquoted_field(row_buffer, input, index, line_end_index, line_number)?;
    expect_comma(input, index, line_end_index, line_number)?;
    append_quoted_field(row_buffer, input, index, line_end_index, line_number)?;
    finish_tuple(input, index, line_end_index, line_number)?;
    write_row(writer, row_buffer, line_number)
}

fn append_unquoted_field(
    row_buffer: &mut Vec<u8>,
    input: &[u8],
    index: &mut usize,
    line_end_index: usize,
    line_number: u64,
) -> Result<(), TrimError> {
    append_field_separator(row_buffer);
    row_buffer.extend_from_slice(parse_unquoted_field(
        input,
        index,
        line_end_index,
        line_number,
    )?);
    Ok(())
}

fn append_quoted_field(
    row_buffer: &mut Vec<u8>,
    input: &[u8],
    index: &mut usize,
    line_end_index: usize,
    line_number: u64,
) -> Result<(), TrimError> {
    append_field_separator(row_buffer);
    skip_ascii_whitespace(input, index, line_end_index);
    expect_byte(input, index, line_end_index, b'\'', line_number)?;

    let mut escape_next = false;
    while *index < line_end_index {
        let byte = input[*index];
        *index += 1;
        if escape_next {
            row_buffer.push(unescape_sql_byte(byte));
            escape_next = false;
            continue;
        }
        if byte == b'\\' {
            escape_next = true;
            continue;
        }
        if byte == b'\'' {
            return Ok(());
        }
        row_buffer.push(byte);
    }

    Err(trim_error(
        line_number,
        *index,
        "unterminated quoted SQL field",
    ))
}

fn parse_unquoted_field<'a>(
    input: &'a [u8],
    index: &mut usize,
    line_end_index: usize,
    line_number: u64,
) -> Result<&'a [u8], TrimError> {
    skip_ascii_whitespace(input, index, line_end_index);
    let field_start = *index;
    while *index < line_end_index {
        let byte = input[*index];
        if byte == b',' || byte == b')' {
            break;
        }
        *index += 1;
    }
    let field = trim_ascii_whitespace(&input[field_start..*index]);
    if field.is_empty() {
        return Err(trim_error(
            line_number,
            *index,
            "expected unquoted SQL field",
        ));
    }
    Ok(field)
}

fn finish_tuple(
    input: &[u8],
    index: &mut usize,
    line_end_index: usize,
    line_number: u64,
) -> Result<(), TrimError> {
    skip_ascii_whitespace(input, index, line_end_index);
    if *index >= line_end_index {
        return Err(trim_error(
            line_number,
            *index,
            "unexpected end of tuple while finishing row",
        ));
    }
    if input[*index] == b')' {
        *index += 1;
        return Ok(());
    }
    expect_byte(input, index, line_end_index, b',', line_number)?;
    skip_to_tuple_end(input, index, line_end_index, line_number)
}

fn skip_to_tuple_end(
    input: &[u8],
    index: &mut usize,
    line_end_index: usize,
    line_number: u64,
) -> Result<(), TrimError> {
    let mut inside_string = false;
    let mut escape_next = false;

    while *index < line_end_index {
        let byte = input[*index];
        *index += 1;
        if inside_string {
            if escape_next {
                escape_next = false;
                continue;
            }
            if byte == b'\\' {
                escape_next = true;
                continue;
            }
            if byte == b'\'' {
                inside_string = false;
            }
            continue;
        }

        if byte == b'\'' {
            inside_string = true;
            continue;
        }
        if byte == b')' {
            return Ok(());
        }
    }

    Err(trim_error(
        line_number,
        *index,
        "unterminated SQL tuple while skipping remaining fields",
    ))
}

fn write_row<W: Write>(
    writer: &mut W,
    row_buffer: &[u8],
    line_number: u64,
) -> Result<(), TrimError> {
    writer.write_all(row_buffer).map_err(|error| {
        TrimError::new(format!(
            "failed to write row for line {line_number}: {error}"
        ))
    })?;
    writer.write_all(b"\n").map_err(|error| {
        TrimError::new(format!(
            "failed to terminate row for line {line_number}: {error}"
        ))
    })?;
    Ok(())
}

fn skip_tuple_separators(input: &[u8], index: &mut usize, line_end_index: usize) {
    while *index < line_end_index {
        let byte = input[*index];
        if byte == b',' || byte.is_ascii_whitespace() {
            *index += 1;
            continue;
        }
        break;
    }
}

fn skip_ascii_whitespace(input: &[u8], index: &mut usize, line_end_index: usize) {
    while *index < line_end_index && input[*index].is_ascii_whitespace() {
        *index += 1;
    }
}

fn expect_comma(
    input: &[u8],
    index: &mut usize,
    line_end_index: usize,
    line_number: u64,
) -> Result<(), TrimError> {
    expect_byte(input, index, line_end_index, b',', line_number)
}

fn expect_byte(
    input: &[u8],
    index: &mut usize,
    line_end_index: usize,
    expected: u8,
    line_number: u64,
) -> Result<(), TrimError> {
    skip_ascii_whitespace(input, index, line_end_index);
    if *index >= line_end_index {
        return Err(trim_error(
            line_number,
            *index,
            format!("expected byte {:?}, found end of line", expected as char),
        ));
    }
    let actual = input[*index];
    if actual != expected {
        return Err(trim_error(
            line_number,
            *index,
            format!(
                "expected byte {:?}, found {:?}",
                expected as char, actual as char,
            ),
        ));
    }
    *index += 1;
    Ok(())
}

fn append_field_separator(row_buffer: &mut Vec<u8>) {
    if !row_buffer.is_empty() {
        row_buffer.push(b'\t');
    }
}

fn strip_trailing_line_endings(input: &[u8]) -> &[u8] {
    let mut end = input.len();
    while end > 0 && (input[end - 1] == b'\n' || input[end - 1] == b'\r') {
        end -= 1;
    }
    &input[..end]
}

fn trim_ascii_whitespace(input: &[u8]) -> &[u8] {
    let mut start = 0;
    while start < input.len() && input[start].is_ascii_whitespace() {
        start += 1;
    }
    let mut end = input.len();
    while end > start && input[end - 1].is_ascii_whitespace() {
        end -= 1;
    }
    &input[start..end]
}

fn unescape_sql_byte(byte: u8) -> u8 {
    match byte {
        b'0' => 0,
        b'b' => 0x08,
        b'n' => b'\n',
        b'r' => b'\r',
        b't' => b'\t',
        b'Z' => 0x1A,
        b'"' => b'"',
        b'\'' => b'\'',
        b'\\' => b'\\',
        _ => byte,
    }
}

fn trim_error(line_number: u64, byte_offset: usize, message: impl Into<String>) -> TrimError {
    TrimError::new(format!(
        "line {line_number}, byte {byte_offset}: {}",
        message.into(),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    fn trim_line(kind: TrimKind, raw_line: &str) -> String {
        let mut output = Vec::new();
        let mut row_buffer = Vec::new();
        let written_rows =
            trim_insert_line(kind, 1, raw_line.as_bytes(), &mut output, &mut row_buffer).unwrap();
        assert!(written_rows > 0);
        String::from_utf8(output).unwrap()
    }

    #[test]
    fn pages_unescape_sql_escapes() {
        let output = trim_line(
            TrimKind::Pages,
            "INSERT INTO `page` VALUES (1,0,'Girls\\'_Generation_(2011_album)',0,'x'),(2,0,'Knights_Who_Say_\\\"Ni!\\\"',0,'y'),(3,0,'TBWA\\\\Chiat\\\\Day',0,'z');\n",
        );
        assert_eq!(
            output,
            "1\t0\tGirls'_Generation_(2011_album)\t0\n2\t0\tKnights_Who_Say_\"Ni!\"\t0\n3\t0\tTBWA\\Chiat\\Day\t0\n",
        );
    }

    #[test]
    fn pages_preserve_titles_containing_tuple_separator_text() {
        let output = trim_line(
            TrimKind::Pages,
            "INSERT INTO `page` VALUES (71701640,0,'104-2,3,(6),(7),11',0,'x'),(71701649,0,'2022_Binh_Duong_karaoke_bar_fire',0,'y');\n",
        );
        assert_eq!(
            output,
            "71701640\t0\t104-2,3,(6),(7),11\t0\n71701649\t0\t2022_Binh_Duong_karaoke_bar_fire\t0\n",
        );
    }

    #[test]
    fn redirects_preserve_titles_containing_tuple_separator_text() {
        let output = trim_line(
            TrimKind::Redirects,
            "INSERT INTO `redirect` VALUES (5,0,'104-2,3,(6),(7),11',NULL,NULL),(6,0,'Fruit',NULL,NULL);\n",
        );
        assert_eq!(output, "5\t0\t104-2,3,(6),(7),11\n6\t0\tFruit\n");
    }

    #[test]
    fn linktargets_preserve_titles_containing_tuple_separator_text() {
        let output = trim_line(
            TrimKind::Targets,
            "INSERT INTO `linktarget` VALUES (11,0,'104-2,3,(6),(7),11'),(12,0,'Fruit');\n",
        );
        assert_eq!(output, "11\t0\t104-2,3,(6),(7),11\n12\t0\tFruit\n");
    }

    #[test]
    fn pagelinks_extract_numeric_fields() {
        let output = trim_line(
            TrimKind::Links,
            "INSERT INTO `pagelinks` VALUES (1,0,11),(2,1,12);\n",
        );
        assert_eq!(output, "1\t0\t11\n2\t1\t12\n");
    }

    #[test]
    fn non_insert_lines_are_skipped() {
        let mut output = Vec::new();
        let mut row_buffer = Vec::new();
        let written_rows = trim_insert_line(
            TrimKind::Pages,
            1,
            b"CREATE TABLE `page` (...);\n",
            &mut output,
            &mut row_buffer,
        )
        .unwrap();
        assert_eq!(written_rows, 0);
        assert!(output.is_empty());
    }

    #[test]
    fn trim_reader_reports_processed_lines_and_written_rows() {
        let mut reader = Cursor::new(
            b"CREATE TABLE `page` (...);\nINSERT INTO `page` VALUES (1,0,'Apple',0,'x'),(2,1,'Talk:Apple',0,'y');\n",
        );
        let mut output = Vec::new();
        let stats = trim_reader_to_writer(TrimKind::Pages, &mut reader, &mut output).unwrap();
        assert_eq!(
            stats,
            TrimStats {
                processed_lines: 2,
                written_rows: 2,
            },
        );
        assert_eq!(
            String::from_utf8(output).unwrap(),
            "1\t0\tApple\t0\n2\t1\tTalk:Apple\t0\n",
        );
    }
}
