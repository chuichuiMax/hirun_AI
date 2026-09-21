//go:build !embed

package presetfonts

import (
	"io/fs"
	"os"
)

// Development builds read the bind-mounted resources instead of embedding
// hundreds of MiB on every Air rebuild.
var files = diskFiles()

func diskFiles() fs.FS {
	for _, dir := range []string{"internal/presetfonts/fonts", "fonts"} {
		if _, err := os.Stat(dir); err == nil {
			return os.DirFS(dir)
		}
	}
	return os.DirFS("internal/presetfonts/fonts")
}
