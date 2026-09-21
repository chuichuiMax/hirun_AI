// Package presetfonts contains the fonts shipped with the Xiaohongshu
// template zone. The files are embedded so both source builds and the
// self-contained production binary carry the same deployment resources.
package presetfonts

import (
	"context"
	"fmt"
	"io/fs"

	"hycanvas/backend/internal/fontlibrary"
)

// Import adds bundled fonts to the persistent public catalogue. Existing
// content-hash matches are skipped; missing storage objects are repaired.
func Import(ctx context.Context, library *fontlibrary.Service) (imported, skipped int, errs []error) {
	err := fs.WalkDir(files, ".", func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			return nil
		}
		data, readErr := fs.ReadFile(files, path)
		if readErr != nil {
			return readErr
		}
		_, added, ensureErr := library.EnsurePreset(ctx, data)
		if ensureErr != nil {
			errs = append(errs, fmt.Errorf("%s: %w", path, ensureErr))
			return nil
		}
		if added {
			imported++
		} else {
			skipped++
		}
		return nil
	})
	if err != nil {
		errs = append(errs, err)
	}
	return imported, skipped, errs
}
