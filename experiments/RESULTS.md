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
