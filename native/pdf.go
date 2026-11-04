package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"sort"
	"strconv"
	"strings"
	"unicode/utf8"

	pdf "github.com/giraffesyo/pdf"
	"github.com/giraffesyo/pdf/ocr/tesseract"
)

type pdfRequest struct {
	path       string
	first      int
	last       int
	ocrMissing bool
}

func parsePDFRequest(args []string, command string, pageLimit int, allowOCR bool) (pdfRequest, error) {
	usage := "usage: " + command + " INPUT.pdf [FIRST_PAGE [LAST_PAGE]]"
	if allowOCR {
		usage += " [--ocr-missing]"
	}
	if len(args) == 1 && args[0] == "--help" {
		fmt.Println("Usage: agent-tools-native " + command + " INPUT.pdf [FIRST_PAGE [LAST_PAGE]]")
		return pdfRequest{}, nil
	}
	filtered := make([]string, 0, len(args))
	ocrMissing := false
	for _, arg := range args {
		if arg == "--ocr-missing" && allowOCR {
			ocrMissing = true
		} else {
			filtered = append(filtered, arg)
		}
	}
	if len(filtered) < 1 || len(filtered) > 3 {
		return pdfRequest{}, errors.New(usage)
	}
	first, last := 1, 1
	if len(filtered) > 1 {
		value, err := strconv.Atoi(filtered[1])
		if err != nil || value < 1 {
			return pdfRequest{}, errors.New("page numbers must be positive integers")
		}
		first, last = value, value
	}
	if len(filtered) > 2 {
		value, err := strconv.Atoi(filtered[2])
		if err != nil || value < 1 {
			return pdfRequest{}, errors.New("page numbers must be positive integers")
		}
		last = value
	}
	if first > last {
		return pdfRequest{}, errors.New("last page must be greater than or equal to first page")
	}
	if last-first >= pageLimit {
		return pdfRequest{}, fmt.Errorf("at most %d pages may be requested at once", pageLimit)
	}
	return pdfRequest{path: filtered[0], first: first, last: last, ocrMissing: ocrMissing}, nil
}

func extractPDF(request pdfRequest, ocrAll bool, maxOCRPages int) (*pdf.Document, error) {
	f, err := os.Open(request.path)
	if err != nil {
		return nil, fmt.Errorf("could not open PDF: %w", err)
	}
	defer f.Close()
	stat, err := f.Stat()
	if err != nil {
		return nil, err
	}
	options := pdf.Options{
		Concurrency: 1,
		Limits: pdf.Limits{
			MaxStreamBytes: 64 * 1024 * 1024, MaxOperatorsPerPage: 1_000_000,
			MaxGlyphsPerPage: 1_000_000, MaxFormDepth: 64,
			MaxImagesPerPage: 1000, MaxImageBytesPerPage: 32 * 1024 * 1024, MaxImagePixels: 16_000_000,
		},
	}
	if request.last > 0 {
		options.Pages = []pdf.PageRange{{First: request.first, Last: request.last}}
	}
	if request.ocrMissing || ocrAll {
		options.OCR = &tesseract.Engine{Languages: []string{"eng"}, PageSegmentation: 3}
		ocrPages := 0
		options.OCRSelect = func(page pdf.Page) bool {
			if !ocrAll && len(page.Glyphs) > 0 {
				return false
			}
			if page.ImageCount == 0 || ocrPages >= maxOCRPages {
				return false
			}
			ocrPages++
			return true
		}
	}
	doc, err := pdf.ExtractWithOptions(context.Background(), f, stat.Size(), options)
	if err != nil {
		return nil, fmt.Errorf("could not read PDF: %w", err)
	}
	if doc.PageCount < 1 {
		return nil, errors.New("PDF has no pages")
	}
	if request.last > doc.PageCount {
		return nil, fmt.Errorf("page range must be within 1...%d", doc.PageCount)
	}
	return doc, nil
}

func pdfText(args []string) error {
	request, err := parsePDFRequest(args, "pdf-text", 20, true)
	if err != nil || request.path == "" {
		return err
	}
	doc, err := extractPDF(request, false, 5)
	if err != nil {
		return err
	}
	pages := make([]map[string]any, 0, len(doc.Pages))
	incomplete := false
	warnings := collectPDFWarnings(doc)
	incomplete = len(warnings) > 0
	ocrEligible := 0
	for i, page := range doc.Pages {
		text := page.Text()
		noExtractableText := len(page.Glyphs)-page.OCRGlyphs == 0
		method := "pdf-text"
		skipped := false
		if page.OCRGlyphs > 0 {
			method = "tesseract-ocr"
		}
		if request.ocrMissing && noExtractableText && page.ImageCount > 0 {
			ocrEligible++
			if ocrEligible > 5 {
				skipped = true
			} else {
				method = "tesseract-ocr"
			}
		}
		truncated := utf8.RuneCountInString(text) > 12000
		if truncated {
			text = string([]rune(text)[:12000])
		}
		empty := strings.TrimSpace(text) == ""
		if empty || truncated || skipped {
			incomplete = true
		}
		pages = append(pages, map[string]any{
			"page": request.first + i, "text": text, "method": method,
			"characters": utf8.RuneCountInString(page.Text()), "truncated": truncated,
			"no_extractable_text": noExtractableText,
			"no_recognized_text":  noExtractableText && !skipped && empty,
			"ocr_skipped":         skipped,
		})
	}
	return printJSON(map[string]any{"source": request.path, "page_count": doc.PageCount, "pages": pages, "warnings": warnings}, incomplete)
}

func pdfFind(args []string) error {
	if len(args) == 1 && args[0] == "--help" {
		fmt.Println("Usage: agent-tools-native pdf-find INPUT.pdf SEARCH_TEXT")
		return nil
	}
	if len(args) != 2 {
		return errors.New("usage: pdf-find INPUT.pdf SEARCH_TEXT")
	}
	query := args[1]
	if strings.TrimSpace(query) == "" || utf8.RuneCountInString(query) > 256 {
		return errors.New("search text must be nonempty and at most 256 characters")
	}
	doc, err := extractPDF(pdfRequest{path: args[0], first: 1, last: 0}, false, 0)
	if err != nil {
		return err
	}
	if doc.PageCount < 1 {
		return errors.New("PDF has no pages")
	}
	count, noTextCount := 0, 0
	warnings := collectPDFWarnings(doc)
	noTextPages := make([]int, 0, 100)
	matches := make([]map[string]any, 0, 20)
	needle := strings.ToLower(query)
	for i, page := range doc.Pages {
		text := page.Text()
		if strings.TrimSpace(text) == "" {
			noTextCount++
			if len(noTextPages) < 100 {
				noTextPages = append(noTextPages, i+1)
			}
			continue
		}
		folded := strings.ToLower(text)
		position := 0
		for position < len(folded) {
			offset := strings.Index(folded[position:], needle)
			if offset < 0 {
				break
			}
			start := position + offset
			end := start + len(needle)
			count++
			if len(matches) < 20 {
				matches = append(matches, map[string]any{"page": i + 1, "excerpt": textExcerpt(text, start, end)})
			}
			position = end
		}
	}
	truncated := count > 20 || noTextCount > 0 || len(warnings) > 0
	return printJSON(map[string]any{
		"source": args[0], "query": query, "page_count": doc.PageCount,
		"match_count": count, "matches": matches, "matches_truncated": count > 20,
		"no_text_page_count": noTextCount, "no_text_pages": noTextPages,
		"no_text_pages_truncated": noTextCount > 100, "warnings": warnings,
	}, truncated)
}

func textExcerpt(text string, startByte, endByte int) string {
	runes := []rune(text)
	start := utf8.RuneCountInString(text[:startByte])
	end := utf8.RuneCountInString(text[:endByte])
	return string(runes[max(0, start-80):min(len(runes), end+80)])
}

func pdfOCR(args []string) error {
	request, err := parsePDFRequest(args, "pdf-ocr", 5, false)
	if err != nil || request.path == "" {
		return err
	}
	doc, err := extractPDF(request, true, 5)
	if err != nil {
		return err
	}
	pages := make([]map[string]any, 0, len(doc.Pages))
	warnings := collectPDFWarnings(doc)
	incomplete := len(warnings) > 0
	for i, page := range doc.Pages {
		text := page.Text()
		truncated := utf8.RuneCountInString(text) > 12000
		if truncated {
			text = string([]rune(text)[:12000])
		}
		empty := strings.TrimSpace(text) == ""
		if empty || truncated {
			incomplete = true
		}
		pages = append(pages, map[string]any{
			"page": request.first + i, "text": text, "characters": utf8.RuneCountInString(page.Text()),
			"truncated": truncated, "no_recognized_text": empty,
			"image_count": page.ImageCount, "ocr_words": page.OCRGlyphs,
		})
	}
	return printJSON(map[string]any{"source": request.path, "page_count": doc.PageCount, "pages": pages, "warnings": warnings}, incomplete)
}

func collectPDFWarnings(doc *pdf.Document) []string {
	seen := map[string]bool{}
	warnings := make([]string, 0)
	add := func(warning pdf.Warning) {
		message := warning.Error()
		if !seen[message] {
			seen[message] = true
			warnings = append(warnings, message)
		}
	}
	for _, warning := range doc.Warnings {
		add(warning)
	}
	for _, page := range doc.Pages {
		for _, warning := range page.Warnings {
			add(warning)
		}
	}
	sort.Strings(warnings)
	return warnings
}

func printJSON(value any, incomplete bool) error {
	if err := json.NewEncoder(os.Stdout).Encode(value); err != nil {
		return err
	}
	if incomplete {
		os.Exit(1)
	}
	return nil
}
