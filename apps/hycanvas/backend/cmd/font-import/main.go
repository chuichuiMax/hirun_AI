// Command font-import bulk-loads operator-supplied TTF/OTF files into the same
// retained Xiaohongshu font library used by the upload API. It is intentionally
// an operational command, not a second storage format or catalogue.
package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"strings"

	"hycanvas/backend/internal/fontlibrary"
	"hycanvas/backend/internal/platform/db"
	"hycanvas/backend/internal/storage"
)

func main() {
	if len(os.Args) < 2 {
		log.Fatal("usage: font-import <font-file-or-directory> [...]")
	}
	databaseURL := os.Getenv("DATABASE_URL")
	if databaseURL == "" {
		log.Fatal("DATABASE_URL is required")
	}
	ctx := context.Background()
	pool, err := db.Connect(ctx, databaseURL)
	if err != nil {
		log.Fatal(err)
	}
	defer pool.Close()
	store, err := storage.NewFromEnv()
	if err != nil {
		log.Fatal(err)
	}
	library := fontlibrary.NewService(pool, store, nil)

	var paths []string
	for _, root := range os.Args[1:] {
		info, statErr := os.Stat(root)
		if statErr != nil {
			log.Printf("skip %s: %v", root, statErr)
			continue
		}
		if !info.IsDir() {
			paths = append(paths, root)
			continue
		}
		walkErr := filepath.WalkDir(root, func(path string, entry os.DirEntry, walkErr error) error {
			if walkErr != nil {
				return walkErr
			}
			if !entry.IsDir() {
				ext := strings.ToLower(filepath.Ext(entry.Name()))
				if ext == ".ttf" || ext == ".otf" {
					paths = append(paths, path)
				}
			}
			return nil
		})
		if walkErr != nil {
			log.Printf("skip %s: %v", root, walkErr)
		}
	}

	imported, failed := 0, 0
	for _, path := range paths {
		data, readErr := os.ReadFile(path)
		if readErr != nil {
			failed++
			log.Printf("failed %s: %v", path, readErr)
			continue
		}
		font, uploadErr := library.Upload(ctx, "", fontlibrary.ZoneXiaohongshu, data)
		if uploadErr != nil {
			failed++
			log.Printf("failed %s: %v", path, uploadErr)
			continue
		}
		imported++
		fmt.Printf("%s\t%s\t%s\t%d\n", font.ID, font.Family, font.Style, font.Weight)
	}
	fmt.Printf("processed=%d failed=%d\n", imported, failed)
	if failed > 0 {
		os.Exit(1)
	}
}
