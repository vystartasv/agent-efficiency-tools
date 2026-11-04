package main

import (
	"fmt"
	"os"
)

var version = "dev"

func main() {
	if len(os.Args) == 2 && os.Args[1] == "--version" {
		fmt.Printf("agent-tools-native %s\n", version)
		return
	}
	if len(os.Args) < 2 || os.Args[1] == "help" || os.Args[1] == "--help" || os.Args[1] == "-h" {
		fmt.Println(`Usage: agent-tools-native COMMAND [ARGS...]

Commands:
  image-prepare  Resize or convert a raster image
  image-crop     Crop a raster image to PNG
  image-text     Recognize image text with Tesseract
  pdf-text       Extract text from selected PDF pages
  pdf-find       Find text in a PDF
  pdf-ocr        Recognize text in selected PDF pages with Tesseract

Run agent-tools-native COMMAND --help for command usage.`)
		return
	}
	var err error
	switch os.Args[1] {
	case "image-prepare":
		err = imagePrepare(os.Args[2:])
	case "image-crop":
		err = imageCrop(os.Args[2:])
	case "image-text":
		err = imageText(os.Args[2:])
	case "pdf-text":
		err = pdfText(os.Args[2:])
	case "pdf-find":
		err = pdfFind(os.Args[2:])
	case "pdf-ocr":
		err = pdfOCR(os.Args[2:])
	default:
		fmt.Fprintf(os.Stderr, "agent-tools-native: unknown command %q\n", os.Args[1])
		os.Exit(2)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
}
