//go:build embed

package presetfonts

import "embed"

// Production builds carry the deployment fonts inside the self-contained
// HyCanvas binary.
//
//go:embed fonts
var embeddedFiles embed.FS

var files = mustSub(embeddedFiles, "fonts")
