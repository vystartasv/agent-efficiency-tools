package main

import (
	"bytes"
	"compress/zlib"
	"context"
	"fmt"
	"image"
	"image/color"
	"image/png"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	pdf "github.com/giraffesyo/pdf"
	"golang.org/x/image/font"
	"golang.org/x/image/font/gofont/goregular"
	"golang.org/x/image/font/opentype"
	"golang.org/x/image/math/fixed"
)

func TestImagePrepareResizeAndRefuseOverwrite(t *testing.T) {
	dir := t.TempDir()
	input, output := filepath.Join(dir, "input.png"), filepath.Join(dir, "small.png")
	solid := image.NewRGBA(image.Rect(0, 0, 8, 4))
	for y := 0; y < 4; y++ {
		for x := 0; x < 8; x++ {
			solid.Set(x, y, color.RGBA{R: 20, A: 255})
		}
	}
	writePNG(t, input, solid)
	if err := imagePrepare([]string{input, output, "4"}); err != nil {
		t.Fatal(err)
	}
	f, err := os.Open(output)
	if err != nil {
		t.Fatal(err)
	}
	config, err := png.DecodeConfig(f)
	f.Close()
	if err != nil || config.Width != 4 || config.Height != 2 {
		t.Fatalf("resized dimensions = %dx%d, err=%v", config.Width, config.Height, err)
	}
	if err := imagePrepare([]string{input, output, "4"}); err == nil {
		t.Fatal("existing output was overwritten")
	}
}

func TestImageCropCoordinatesAndPixels(t *testing.T) {
	dir := t.TempDir()
	input, output := filepath.Join(dir, "input.png"), filepath.Join(dir, "crop.png")
	img := image.NewRGBA(image.Rect(0, 0, 4, 4))
	for y := 0; y < 4; y++ {
		for x := 0; x < 4; x++ {
			if y < 2 {
				img.Set(x, y, color.RGBA{R: 255, A: 255})
			} else {
				img.Set(x, y, color.RGBA{B: 255, A: 255})
			}
		}
	}
	writePNG(t, input, img)
	if err := imageCrop([]string{input, output, "1", "2", "2", "1"}); err != nil {
		t.Fatal(err)
	}
	f, err := os.Open(output)
	if err != nil {
		t.Fatal(err)
	}
	crop, err := png.Decode(f)
	f.Close()
	if err != nil {
		t.Fatal(err)
	}
	got := color.RGBAModel.Convert(crop.At(0, 0)).(color.RGBA)
	if got.B < 240 || got.R > 10 {
		t.Fatalf("cropped pixel = %#v, want blue", got)
	}
	if err := imageCrop([]string{input, filepath.Join(dir, "bad.png"), "3", "3", "2", "2"}); err == nil {
		t.Fatal("out-of-bounds crop succeeded")
	}
}

func TestImageTextParsesTSVAndCoordinates(t *testing.T) {
	tsv := "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n" +
		"5\t1\t1\t1\t1\t1\t20\t10\t30\t12\t90\tHELLO\n" +
		"5\t1\t1\t1\t1\t2\t55\t10\t24\t12\t80\tWORLD\n"
	regions, text, err := parseTSV(strings.NewReader(tsv), 100, 50)
	if err != nil {
		t.Fatal(err)
	}
	if text != "HELLO WORLD" || len(regions) != 1 || regions[0].Text != text {
		t.Fatalf("text/regions = %q, %#v", text, regions)
	}
	if regions[0].Confidence != 85 || regions[0].X != .2 || regions[0].Y != .2 || regions[0].Width != .59 || regions[0].Height != .24 {
		t.Fatalf("region = %#v", regions[0])
	}
}

func TestExifOrientationParserFlagsUnnormalizedPixels(t *testing.T) {
	data := []byte{'I', 'I', 42, 0, 8, 0, 0, 0, 1, 0, 0x12, 0x01, 3, 0, 1, 0, 0, 0, 6, 0, 0, 0, 0, 0, 0, 0}
	path := filepath.Join(t.TempDir(), "oriented.tiff")
	if err := os.WriteFile(path, data, 0600); err != nil {
		t.Fatal(err)
	}
	orientation, err := imageOrientation(path, "tiff")
	if err != nil || orientation != 6 {
		t.Fatalf("orientation = %d, err=%v", orientation, err)
	}
	jpeg := append([]byte{0xff, 0xd8, 0xff, 0xe1, 0, 34}, []byte("Exif\x00\x00")...)
	jpeg = append(jpeg, data...)
	jpeg = append(jpeg, 0xff, 0xda)
	path = filepath.Join(t.TempDir(), "oriented.jpg")
	if err := os.WriteFile(path, jpeg, 0600); err != nil {
		t.Fatal(err)
	}
	orientation, err = imageOrientation(path, "jpeg")
	if err != nil || orientation != 6 {
		t.Fatalf("JPEG orientation = %d, err=%v", orientation, err)
	}
}

func TestPDFTextExtractsRealDocumentFixture(t *testing.T) {
	data := minimalTextPDF("HELLO PAGE ONE", "ORDER 7264 READY")
	path := filepath.Join(t.TempDir(), "sample.pdf")
	if err := os.WriteFile(path, data, 0600); err != nil {
		t.Fatal(err)
	}
	doc, err := extractPDF(pdfRequest{path: path, first: 1, last: 1}, false, 0)
	if err != nil {
		t.Fatal(err)
	}
	if doc.PageCount != 1 || !strings.Contains(doc.Pages[0].Text(), "ORDER 7264 READY") {
		t.Fatalf("unexpected extraction: pages=%d text=%q", doc.PageCount, doc.Pages[0].Text())
	}
}

func TestPDFOCRExtractsEmbeddedImageWhenTesseractIsInstalled(t *testing.T) {
	if _, err := exec.LookPath("tesseract"); err != nil {
		t.Skip("requires Tesseract")
	}
	data := imageOnlyPDF(t, "ORDER 7264 READY")
	path := filepath.Join(t.TempDir(), "scan.pdf")
	if err := os.WriteFile(path, data, 0600); err != nil {
		t.Fatal(err)
	}
	doc, err := extractPDF(pdfRequest{path: path, first: 1, last: 1, ocrMissing: true}, false, 5)
	if err != nil {
		t.Fatal(err)
	}
	if len(doc.Pages) != 1 || doc.Pages[0].OCRGlyphs == 0 || !strings.Contains(doc.Pages[0].Text(), "7264") {
		t.Fatalf("OCR did not recover the fixture text: %#v", doc.Pages)
	}
}

func writePNG(t *testing.T, path string, img image.Image) {
	t.Helper()
	f, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := png.Encode(f, img); err != nil {
		f.Close()
		t.Fatal(err)
	}
	if err := f.Close(); err != nil {
		t.Fatal(err)
	}
}

func minimalTextPDF(lines ...string) []byte {
	content := "BT /F1 12 Tf 20 180 Td "
	for i, line := range lines {
		if i > 0 {
			content += "T* "
		}
		content += "(" + line + ") Tj "
	}
	content += "ET"
	objects := []string{
		"<< /Type /Catalog /Pages 2 0 R >>",
		"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
		"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
		"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
		fmt.Sprintf("<< /Length %d >>\nstream\n%s\nendstream", len(content), content),
	}
	var b bytes.Buffer
	b.WriteString("%PDF-1.4\n")
	offsets := make([]int, len(objects))
	for i, object := range objects {
		offsets[i] = b.Len()
		fmt.Fprintf(&b, "%d 0 obj\n%s\nendobj\n", i+1, object)
	}
	xref := b.Len()
	fmt.Fprintf(&b, "xref\n0 %d\n0000000000 65535 f \n", len(objects)+1)
	for _, offset := range offsets {
		fmt.Fprintf(&b, "%010d 00000 n \n", offset)
	}
	fmt.Fprintf(&b, "trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n", len(objects)+1, xref)
	return b.Bytes()
}

func imageOnlyPDF(t *testing.T, text string) []byte {
	t.Helper()
	faceData, err := opentype.Parse(goregular.TTF)
	if err != nil {
		t.Fatal(err)
	}
	face, err := opentype.NewFace(faceData, &opentype.FaceOptions{Size: 84, DPI: 72, Hinting: font.HintingFull})
	if err != nil {
		t.Fatal(err)
	}
	const width, height = 1500, 260
	img := image.NewRGBA(image.Rect(0, 0, width, height))
	for y := 0; y < height; y++ {
		for x := 0; x < width; x++ {
			img.Set(x, y, color.White)
		}
	}
	drawer := font.Drawer{Dst: img, Src: image.Black, Face: face, Dot: fixed.P(30, 165)}
	drawer.DrawString(text)
	face.Close()
	var raw bytes.Buffer
	for y := 0; y < height; y++ {
		for x := 0; x < width; x++ {
			r, g, b, _ := img.At(x, y).RGBA()
			raw.Write([]byte{byte(r >> 8), byte(g >> 8), byte(b >> 8)})
		}
	}
	var compressed bytes.Buffer
	zw := zlib.NewWriter(&compressed)
	if _, err := zw.Write(raw.Bytes()); err != nil {
		t.Fatal(err)
	}
	if err := zw.Close(); err != nil {
		t.Fatal(err)
	}
	imageObject := fmt.Sprintf("<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n", width, height, compressed.Len())
	imageStream := append([]byte(imageObject), compressed.Bytes()...)
	imageStream = append(imageStream, []byte("\nendstream")...)
	content := []byte("q 500 0 0 86 20 9 cm /Im0 Do Q")
	objects := [][]byte{
		[]byte("<< /Type /Catalog /Pages 2 0 R >>"),
		[]byte("<< /Type /Pages /Kids [3 0 R] /Count 1 >>"),
		[]byte("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 104] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>"),
		imageStream,
		[]byte(fmt.Sprintf("<< /Length %d >>\nstream\n%s\nendstream", len(content), content)),
	}
	var out bytes.Buffer
	out.WriteString("%PDF-1.4\n")
	offsets := make([]int, len(objects))
	for i, object := range objects {
		offsets[i] = out.Len()
		fmt.Fprintf(&out, "%d 0 obj\n", i+1)
		out.Write(object)
		out.WriteString("\nendobj\n")
	}
	xref := out.Len()
	fmt.Fprintf(&out, "xref\n0 %d\n0000000000 65535 f \n", len(objects)+1)
	for _, offset := range offsets {
		fmt.Fprintf(&out, "%010d 00000 n \n", offset)
	}
	fmt.Fprintf(&out, "trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n", len(objects)+1, xref)
	// Sanity-check the generated fixture with the same PDF reader before OCR.
	doc, err := pdf.Extract(context.Background(), bytes.NewReader(out.Bytes()), int64(out.Len()))
	if err != nil || doc.PageCount != 1 {
		t.Fatalf("could not generate image-only PDF fixture: pages=%v err=%v", doc, err)
	}
	return out.Bytes()
}
