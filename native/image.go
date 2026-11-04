package main

import (
	"bytes"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"image"
	"image/color"
	"image/jpeg"
	"image/png"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"

	_ "golang.org/x/image/bmp"
	"golang.org/x/image/draw"
	_ "golang.org/x/image/tiff"
	_ "golang.org/x/image/webp"
	_ "image/gif"
)

func imagePrepare(args []string) error {
	if len(args) == 1 && args[0] == "--help" {
		fmt.Println("Usage: agent-tools-native image-prepare INPUT OUTPUT [MAX_DIMENSION] [JPEG_QUALITY]")
		return nil
	}
	if len(args) < 2 || len(args) > 4 {
		return errors.New("usage: image-prepare INPUT OUTPUT [MAX_DIMENSION] [JPEG_QUALITY]")
	}
	maxDimension := 1600
	if len(args) > 2 {
		value, err := strconv.Atoi(args[2])
		if err != nil || value < 1 || value > 100000 {
			return errors.New("MAX_DIMENSION must be an integer from 1 to 100000")
		}
		maxDimension = value
	}
	quality := 90
	if len(args) > 3 {
		value, err := strconv.Atoi(args[3])
		if err != nil || value < 1 || value > 100 || !isJPEG(args[1]) {
			return errors.New("JPEG_QUALITY requires JPEG output and must be an integer from 1 to 100")
		}
		quality = value
	}
	if !isPNG(args[1]) && !isJPEG(args[1]) {
		return errors.New("output must end in .jpg, .jpeg, or .png")
	}
	config, format, err := decodeConfig(args[0])
	if err != nil {
		return err
	}
	if isPNG(args[1]) && format == "png" && config.Width <= maxDimension && config.Height <= maxDimension && len(args) < 4 {
		return copyExclusive(args[0], args[1])
	}
	source, _, err := decodeImage(args[0])
	if err != nil {
		return err
	}
	w, h := resizedSize(config.Width, config.Height, maxDimension)
	var output image.Image = source
	if w != config.Width || h != config.Height {
		resized := image.NewRGBA(image.Rect(0, 0, w, h))
		draw.CatmullRom.Scale(resized, resized.Bounds(), source, source.Bounds(), draw.Over, nil)
		output = resized
	}
	return writeImage(args[1], output, quality)
}

func imageCrop(args []string) error {
	if len(args) == 1 && args[0] == "--help" {
		fmt.Println("Usage: agent-tools-native image-crop INPUT OUTPUT.png X Y WIDTH HEIGHT")
		return nil
	}
	if len(args) != 6 {
		return errors.New("usage: image-crop INPUT OUTPUT.png X Y WIDTH HEIGHT")
	}
	if !isPNG(args[1]) {
		return errors.New("output must be a PNG file")
	}
	coordinates := [4]int{}
	for i := range coordinates {
		value, err := strconv.Atoi(args[i+2])
		if err != nil {
			return errors.New("coordinates must be nonnegative integers and dimensions positive integers")
		}
		coordinates[i] = value
	}
	x, y, width, height := coordinates[0], coordinates[1], coordinates[2], coordinates[3]
	if x < 0 || y < 0 || width <= 0 || height <= 0 {
		return errors.New("coordinates must be nonnegative integers and dimensions positive integers")
	}
	decoded, format, err := decodeImage(args[0])
	if err != nil {
		return err
	}
	if format == "jpeg" || format == "tiff" {
		orientation, err := imageOrientation(args[0], format)
		if err != nil {
			return err
		}
		if orientation != 1 {
			return errors.New("image orientation is not normalized; normalize it before cropping")
		}
	}
	bounds := decoded.Bounds()
	if x > bounds.Dx() || y > bounds.Dy() || width > bounds.Dx()-x || height > bounds.Dy()-y {
		return fmt.Errorf("crop extends beyond image bounds %dx%d", bounds.Dx(), bounds.Dy())
	}
	region := image.Rect(bounds.Min.X+x, bounds.Min.Y+y, bounds.Min.X+x+width, bounds.Min.Y+y+height)
	sub, ok := decoded.(interface {
		SubImage(image.Rectangle) image.Image
	})
	if !ok {
		return errors.New("image format does not support cropping")
	}
	if err := writeImage(args[1], sub.SubImage(region), 90); err != nil {
		return err
	}
	fmt.Printf("%s\n  pixelWidth: %d\n  pixelHeight: %d\n", args[1], width, height)
	return nil
}

func imageOrientation(path, format string) (int, error) {
	f, err := os.Open(path)
	if err != nil {
		return 0, err
	}
	defer f.Close()
	data, err := io.ReadAll(io.LimitReader(f, 1<<20))
	if err != nil {
		return 0, err
	}
	if format == "tiff" {
		return exifOrientation(data)
	}
	if len(data) < 4 || data[0] != 0xff || data[1] != 0xd8 {
		return 1, nil
	}
	for offset := 2; offset+4 <= len(data); {
		if data[offset] != 0xff {
			return 1, nil
		}
		for offset < len(data) && data[offset] == 0xff {
			offset++
		}
		if offset >= len(data) {
			break
		}
		marker := data[offset]
		offset++
		if marker == 0xd9 || marker == 0xda {
			break
		}
		if marker == 0xd8 || marker == 0x01 || marker >= 0xd0 && marker <= 0xd7 {
			continue
		}
		length := int(binary.BigEndian.Uint16(data[offset : offset+2]))
		if length < 2 || offset+length > len(data) {
			return 1, nil
		}
		segment := data[offset+2 : offset+length]
		if marker == 0xe1 && bytes.HasPrefix(segment, []byte("Exif\x00\x00")) {
			return exifOrientation(segment[6:])
		}
		offset += length
	}
	return 1, nil
}

func exifOrientation(data []byte) (int, error) {
	if len(data) < 8 {
		return 0, errors.New("invalid EXIF orientation metadata")
	}
	var order binary.ByteOrder
	switch string(data[:2]) {
	case "II":
		order = binary.LittleEndian
	case "MM":
		order = binary.BigEndian
	default:
		return 0, errors.New("invalid EXIF byte order")
	}
	if order.Uint16(data[2:4]) != 42 {
		return 0, errors.New("invalid EXIF header")
	}
	ifd := int(order.Uint32(data[4:8]))
	if ifd < 8 || ifd+2 > len(data) {
		return 0, errors.New("invalid EXIF directory")
	}
	count := int(order.Uint16(data[ifd : ifd+2]))
	for i := 0; i < count; i++ {
		entry := ifd + 2 + i*12
		if entry+12 > len(data) {
			return 0, errors.New("invalid EXIF directory entry")
		}
		if order.Uint16(data[entry:entry+2]) != 0x0112 {
			continue
		}
		if order.Uint16(data[entry+2:entry+4]) != 3 || order.Uint32(data[entry+4:entry+8]) < 1 {
			return 0, errors.New("invalid EXIF orientation field")
		}
		orientation := int(order.Uint16(data[entry+8 : entry+10]))
		if orientation < 1 || orientation > 8 {
			return 0, errors.New("invalid EXIF orientation value")
		}
		return orientation, nil
	}
	return 1, nil
}

func decodeConfig(path string) (image.Config, string, error) {
	f, err := os.Open(path)
	if err != nil {
		return image.Config{}, "", fmt.Errorf("could not open input: %w", err)
	}
	defer f.Close()
	config, format, err := image.DecodeConfig(f)
	if err != nil {
		return image.Config{}, "", fmt.Errorf("could not decode input image: %w", err)
	}
	if config.Width < 1 || config.Height < 1 || int64(config.Width)*int64(config.Height) > 100_000_000 {
		return image.Config{}, "", errors.New("image dimensions must be between 1 and 100000 pixels per edge and at most 100 million pixels")
	}
	return config, format, nil
}

func decodeImage(path string) (image.Image, string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, "", fmt.Errorf("could not open input: %w", err)
	}
	defer f.Close()
	img, format, err := image.Decode(f)
	if err != nil {
		return nil, "", fmt.Errorf("could not decode input image: %w", err)
	}
	b := img.Bounds()
	if b.Dx() < 1 || b.Dy() < 1 || int64(b.Dx())*int64(b.Dy()) > 100_000_000 {
		return nil, "", errors.New("image dimensions exceed 100 million pixels")
	}
	return img, format, nil
}

func resizedSize(width, height, limit int) (int, int) {
	if width <= limit && height <= limit {
		return width, height
	}
	scale := float64(limit) / float64(max(width, height))
	return max(1, int(float64(width)*scale)), max(1, int(float64(height)*scale))
}

func writeImage(path string, img image.Image, quality int) error {
	return writeExclusive(path, func(w io.Writer) error {
		if isJPEG(path) {
			// JPEG has no alpha channel; composite transparent pixels onto white.
			bounds := img.Bounds()
			background := image.NewRGBA(image.Rect(0, 0, bounds.Dx(), bounds.Dy()))
			for y := 0; y < bounds.Dy(); y++ {
				for x := 0; x < bounds.Dx(); x++ {
					background.Set(x, y, color.White)
				}
			}
			draw.Draw(background, background.Bounds(), img, bounds.Min, draw.Over)
			return jpeg.Encode(w, background, &jpeg.Options{Quality: quality})
		}
		return png.Encode(w, img)
	})
}

func writeExclusive(path string, encode func(io.Writer) error) error {
	if _, err := os.Lstat(path); err == nil {
		return fmt.Errorf("output already exists: %s", path)
	} else if !os.IsNotExist(err) {
		return fmt.Errorf("could not inspect output: %w", err)
	}
	dir := filepath.Dir(path)
	tmp, err := os.CreateTemp(dir, ".agent-tools-native-*")
	if err != nil {
		return fmt.Errorf("could not create temporary output: %w", err)
	}
	tmpName := tmp.Name()
	defer os.Remove(tmpName)
	if err = encode(tmp); err == nil {
		err = tmp.Sync()
	}
	if closeErr := tmp.Close(); err == nil {
		err = closeErr
	}
	if err != nil {
		return fmt.Errorf("could not write output: %w", err)
	}
	if err := os.Link(tmpName, path); err != nil {
		return fmt.Errorf("could not create output (it may already exist): %w", err)
	}
	return nil
}

func copyExclusive(input, output string) error {
	return writeExclusive(output, func(w io.Writer) error {
		f, err := os.Open(input)
		if err != nil {
			return err
		}
		defer f.Close()
		_, err = io.Copy(w, f)
		return err
	})
}

func isPNG(path string) bool {
	return strings.EqualFold(filepath.Ext(path), ".png")
}

func isJPEG(path string) bool {
	ext := strings.ToLower(filepath.Ext(path))
	return ext == ".jpg" || ext == ".jpeg"
}

type wordRegion struct {
	Text       string  `json:"text"`
	Confidence float64 `json:"confidence"`
	X          float64 `json:"x"`
	Y          float64 `json:"y"`
	Width      float64 `json:"width"`
	Height     float64 `json:"height"`
}

type imageTextResult struct {
	Source           string       `json:"source"`
	Characters       int          `json:"characters"`
	Text             string       `json:"text"`
	Truncated        bool         `json:"truncated"`
	NoRecognizedText bool         `json:"no_recognized_text"`
	Regions          []wordRegion `json:"regions,omitempty"`
}

func imageText(args []string) error {
	if len(args) == 1 && args[0] == "--help" {
		fmt.Println("Usage: agent-tools-native image-text IMAGE [--json] [--regions] [--max-chars N]")
		return nil
	}
	if len(args) < 1 {
		return errors.New("usage: image-text IMAGE [--json] [--regions] [--max-chars N]")
	}
	maxChars, wantJSON, wantRegions := 12000, false, false
	for i := 1; i < len(args); i++ {
		switch args[i] {
		case "--json":
			wantJSON = true
		case "--regions":
			wantRegions = true
		case "--max-chars":
			if i+1 >= len(args) {
				return errors.New("--max-chars requires a value")
			}
			i++
			value, err := strconv.Atoi(args[i])
			if err != nil || value < 1 || value > 100000 {
				return errors.New("--max-chars must be between 1 and 100000")
			}
			maxChars = value
		default:
			return fmt.Errorf("unknown option %q", args[i])
		}
	}
	if wantRegions {
		wantJSON = true
	}
	config, _, err := decodeConfig(args[0])
	if err != nil {
		return err
	}
	inputDir := filepath.Dir(args[0])
	inputName := filepath.Base(args[0])
	cmd := exec.Command("tesseract", inputName, "stdout", "--psm", "6", "tsv")
	cmd.Dir = inputDir
	data, err := cmd.Output()
	if err != nil {
		return fmt.Errorf("Tesseract OCR failed or is not installed: %w", err)
	}
	regions, text, err := parseTSV(bytes.NewReader(data), config.Width, config.Height)
	if err != nil {
		return err
	}
	characters := len([]rune(strings.TrimRight(text, "\n")))
	truncated := characters > maxChars
	if truncated {
		text = string([]rune(text)[:maxChars])
	}
	result := imageTextResult{Source: args[0], Characters: characters, Text: strings.TrimRight(text, "\n"), Truncated: truncated}
	result.NoRecognizedText = strings.TrimSpace(text) == ""
	if wantRegions {
		result.Regions = regions
	}
	if wantJSON {
		if err := json.NewEncoder(os.Stdout).Encode(result); err != nil {
			return err
		}
	} else {
		fmt.Println(result.Text)
	}
	if result.NoRecognizedText || result.Truncated {
		os.Exit(1)
	}
	return nil
}

func parseTSV(r io.Reader, width, height int) ([]wordRegion, string, error) {
	data, err := io.ReadAll(r)
	if err != nil {
		return nil, "", err
	}
	lines := bytes.Split(bytes.TrimSpace(data), []byte("\n"))
	if len(lines) < 2 {
		return nil, "", errors.New("Tesseract returned an invalid TSV result")
	}
	type lineData struct {
		text       []string
		confidence float64
		count      int
		left, top  int
		right, bot int
	}
	lineMap := map[string]*lineData{}
	var order []string
	for _, raw := range lines[1:] {
		fields := strings.SplitN(string(raw), "\t", 12)
		if len(fields) != 12 || fields[0] != "5" || fields[11] == "" {
			continue
		}
		key := strings.Join(fields[1:5], ":")
		left, e1 := strconv.Atoi(fields[6])
		top, e2 := strconv.Atoi(fields[7])
		w, e3 := strconv.Atoi(fields[8])
		h, e4 := strconv.Atoi(fields[9])
		confidence, e5 := strconv.ParseFloat(fields[10], 64)
		if e1 != nil || e2 != nil || e3 != nil || e4 != nil || e5 != nil {
			continue
		}
		entry := lineMap[key]
		if entry == nil {
			entry = &lineData{left: left, top: top, right: left + w, bot: top + h}
			lineMap[key] = entry
			order = append(order, key)
		}
		entry.text = append(entry.text, fields[11])
		entry.confidence += confidence
		entry.count++
		entry.left = min(entry.left, left)
		entry.top = min(entry.top, top)
		entry.right = max(entry.right, left+w)
		entry.bot = max(entry.bot, top+h)
	}
	regions := make([]wordRegion, 0, len(order))
	text := make([]string, 0, len(order))
	for _, key := range order {
		entry := lineMap[key]
		regions = append(regions, wordRegion{Text: strings.Join(entry.text, " "), Confidence: entry.confidence / float64(entry.count),
			X: float64(entry.left) / float64(width), Y: float64(entry.top) / float64(height),
			Width: float64(entry.right-entry.left) / float64(width), Height: float64(entry.bot-entry.top) / float64(height)})
		text = append(text, strings.Join(entry.text, " "))
	}
	return regions, strings.Join(text, "\n"), nil
}
