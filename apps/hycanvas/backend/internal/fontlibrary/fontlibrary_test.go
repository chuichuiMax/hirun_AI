package fontlibrary

import (
	"os"
	"testing"
)

func TestInspectFontReadsInternalMetadata(t *testing.T) {
	data, err := os.ReadFile("../render/fonts/LiberationSans-Regular.ttf")
	if err != nil {
		t.Fatal(err)
	}
	meta, err := inspectFont(data)
	if err != nil {
		t.Fatal(err)
	}
	if meta.Family != "Liberation Sans" {
		t.Fatalf("family = %q", meta.Family)
	}
	if meta.Style != "Regular" || meta.Weight != 400 {
		t.Fatalf("style/weight = %q/%d", meta.Style, meta.Weight)
	}
	if meta.Format != "ttf" || meta.MimeType != "font/ttf" {
		t.Fatalf("format = %q (%q)", meta.Format, meta.MimeType)
	}
}

func TestInspectFontRejectsNonFontBytes(t *testing.T) {
	if _, err := inspectFont([]byte("not a font file")); err == nil {
		t.Fatal("non-font bytes were accepted")
	}
}

func TestStyleWeight(t *testing.T) {
	tests := map[string]int{
		"Extra Light":     200,
		"SemiBold Italic": 600,
		"Bold":            700,
		"Black":           900,
		"Regular":         400,
	}
	for style, want := range tests {
		if got := styleWeight(style); got != want {
			t.Errorf("styleWeight(%q) = %d, want %d", style, got, want)
		}
	}
}

func TestEnsurePresetRejectsEmptyBytes(t *testing.T) {
	var service Service
	if _, _, err := service.EnsurePreset(nil, nil); err == nil {
		t.Fatal("empty preset bytes were accepted")
	}
}
