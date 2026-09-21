package presetfonts

import (
	"crypto/sha256"
	"encoding/hex"
	"io/fs"
	"path/filepath"
	"strings"
	"testing"
)

func TestBundledFontsAreMaterializedAndNamedByDigest(t *testing.T) {
	count := 0
	var total int64
	err := fs.WalkDir(files, ".", func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			return nil
		}
		data, err := fs.ReadFile(files, path)
		if err != nil {
			return err
		}
		if len(data) < 4 || (string(data[:4]) != "OTTO" && string(data[:4]) != "\x00\x01\x00\x00" && string(data[:4]) != "true") {
			t.Fatalf("%s is not a materialized TTF/OTF file", path)
		}
		sum := sha256.Sum256(data)
		want := strings.TrimSuffix(filepath.Base(path), filepath.Ext(path))
		if got := hex.EncodeToString(sum[:]); got != want {
			t.Fatalf("%s digest = %s", path, got)
		}
		count++
		total += int64(len(data))
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if count != 25 || total != 268448588 {
		t.Fatalf("bundled fonts = %d files / %d bytes", count, total)
	}
}
