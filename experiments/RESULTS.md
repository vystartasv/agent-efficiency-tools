# Synthetic experiment results

These are single-run fixture results, not broad performance claims. The fixtures contain no project data.

| Tool | Measurement | Limitation |
| --- | --- | --- |
| Image resize + OCR | A 2,400 × 1,200 synthetic image retained 4/4 lines at 1,600 × 800 and 3/4 at 800 × 400. | Clean English text does not represent varied layouts or languages. File bytes are not image tokens. |
| Log scan | A 5,003-line log fell from 65,022 to 180 `o200k_base` tokens; the excerpt retained the seeded error and expected/actual values. | Pattern matches are leads. Unfamiliar errors can be missed. |
| Browser `--main` | A page with 250 navigation links fell from 1,016 to 15 text tokens and retained its seeded result. | This only tests a page with a semantic `<main>` element. |
| Batch OCR | Three images produced identical text in one process; elapsed time was 0.45 s vs 1.11 s. Output grew from 213 to 224 tokens. | This saves process overhead, not output tokens. Text was large, clean, and synthetic. |
| Test report | A 1,001-case JUnit fixture returned the one seeded failure in 265 bytes. | Only failures represented in the report can be recovered. |
| Output capture | A synthetic exit-7 command retained all output in a private file and returned exit 7 with a bounded excerpt. | Excerpts can omit important context; retain the source file. |

Reproduce with `python3 experiments/log_scan.py`, `python3 experiments/browser_scope.py`, and `python3 experiments/image_batch_ocr.py`. Token measurements require `tiktoken`; other scripts report bytes when it is unavailable.

These tests do not establish total task cost or correctness on arbitrary inputs. Measure representative tasks with the target model and inspect the original evidence when details matter.

## Cross-platform implementation comparison (2026-11-04)

`python3 experiments/cross_platform_benchmark.py --native-bin native/agent-tools-native` compares the current macOS commands with the Go binary and optional portable engines. It generates a local screenshot, a selectable-text PDF, and a scanned PDF; OCR text stays in memory. It needs macOS Swift, `sips`, and the Homebrew `imagemagick`, `tesseract`, and `poppler` tools. To compare a real corpus, add `--pdf-dir PATH`.

On this Apple Silicon Mac, using medians of nine fresh command processes (five for PDF OCR):

| Operation | Existing macOS path | Go / portable candidate | Result |
| --- | ---: | ---: | --- |
| Resize 1000 × 500 PNG to 800 px | `sips`: 14.04 ms, 19.3 KB | Go: 20.01 ms, 16.0 KB; ImageMagick: 26.59 ms, 8.6 KB | Keep `sips` on macOS; use Go for supported raster inputs on other platforms. |
| Crop 500 × 250 PNG region | Swift ImageIO: 203.13 ms, 10.8 KB | Go: 10.86 ms, 8.7 KB; ImageMagick: 12.14 ms, 5.7 KB | Go is about 19× faster than the Swift script on this fixture and needs no external image runtime. |
| Screenshot OCR | Vision: 389.87 ms | Tesseract: 61.57 ms | Both returned the exact seeded text. One clean fixture does not establish general OCR quality. |
| Selectable PDF text | PDFKit/Swift: 310.98 ms | Go PDF: 2.94 ms; Poppler: 11.17 ms | All found the seeded ID; Poppler changed reading order on this generated layout. |
| Scanned PDF OCR | Vision: 401.75 ms | Go + Tesseract: 63.86 ms; Poppler + Tesseract: 247.95 ms | All returned the exact seeded text. This is still one clean scan. |

The stripped combined Go binary was 5,159,202 bytes on this machine. Cross-compilation succeeded for Windows and Linux. The Go PDF extractor was also run over the 13 redistributable PDFs in the [upstream regression corpus](https://github.com/giraffesyo/pdf/tree/main/testdata/corpus): all files parsed; total command time was 74.82 ms versus 197.75 ms for Poppler; mean per-document word-token recall against Poppler output was 97.22%. That is a comparison to another extractor, not ground-truth accuracy. The upstream package's golden tests separately pin expected text for those documents.

ImageMagick, Tesseract, and Poppler were rejected as bundled replacements: their Homebrew formula payloads alone were 28.7 MB, 26.3 MB, and 34.6 MB, before transitive dependencies. `pdfcpu` was rejected because its content-stream extraction is not selectable-text extraction. The chosen standalone Go binary handles common raster formats and PDF text/search without those runtimes; Tesseract stays optional for OCR. Keep Apple's existing Vision/PDFKit paths in the npm CLI so Mac users retain zero-install OCR and existing platform formats. Real screenshots, varied PDFs, model token use, and complete task outcomes still need broader measurement before making accuracy or token-savings claims.
