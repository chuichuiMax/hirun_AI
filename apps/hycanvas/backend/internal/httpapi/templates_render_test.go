package httpapi

import (
	"bytes"
	"context"
	"encoding/json"
	"image/png"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"

	"hycanvas/backend/internal/apikeys"
	"hycanvas/backend/internal/templates"
)

type publicCatalogDB struct{}

func (publicCatalogDB) QueryRow(context.Context, string, ...any) pgx.Row { return nil }
func (publicCatalogDB) Exec(context.Context, string, ...any) (pgconn.CommandTag, error) {
	return pgconn.CommandTag{}, nil
}
func (publicCatalogDB) Query(_ context.Context, sql string, _ ...any) (pgx.Rows, error) {
	return &publicCatalogRows{collectionQuery: bytes.Contains([]byte(sql), []byte("template_collections"))}, nil
}

type publicCatalogRows struct {
	collectionQuery bool
	read            bool
}

func (r *publicCatalogRows) Close()                                       {}
func (r *publicCatalogRows) Err() error                                   { return nil }
func (r *publicCatalogRows) CommandTag() pgconn.CommandTag                { return pgconn.CommandTag{} }
func (r *publicCatalogRows) FieldDescriptions() []pgconn.FieldDescription { return nil }
func (r *publicCatalogRows) RawValues() [][]byte                          { return nil }
func (r *publicCatalogRows) Conn() *pgx.Conn                              { return nil }
func (r *publicCatalogRows) NextResultSet() bool                          { return false }
func (r *publicCatalogRows) Values() ([]any, error)                       { return nil, nil }
func (r *publicCatalogRows) Next() bool {
	if r.read {
		return false
	}
	r.read = true
	return r.collectionQuery
}
func (r *publicCatalogRows) Scan(dest ...any) error {
	*(dest[0].(*string)) = "category-1"
	*(dest[1].(*string)) = "workspace-1"
	*(dest[2].(*string)) = "内容报价"
	return nil
}

func TestRenderTemplatePreviewCreatesScaledPNG(t *testing.T) {
	file := map[string]any{
		"pages": []any{map[string]any{
			"width": 100.0, "height": 200.0,
			"children": []any{},
		}},
	}

	data, err := renderTemplatePreview(file, nil)
	if err != nil {
		t.Fatalf("renderTemplatePreview: %v", err)
	}
	image, err := png.Decode(bytes.NewReader(data))
	if err != nil {
		t.Fatalf("decode preview PNG: %v", err)
	}
	if image.Bounds().Dx() != 25 || image.Bounds().Dy() != 50 {
		t.Fatalf("preview dimensions = %dx%d, want 25x50", image.Bounds().Dx(), image.Bounds().Dy())
	}
}

func TestRenderTemplateOverlayCreatesTransparentScaledPNG(t *testing.T) {
	color := func(r, g, b float64) map[string]any {
		return map[string]any{"srgb": map[string]any{"r": r, "g": g, "b": b, "a": 1.0}}
	}
	file := map[string]any{
		"pages": []any{map[string]any{
			"width": 100.0, "height": 200.0,
			"background": map[string]any{"type": "solid", "color": color(1, 1, 1)},
			"children": []any{map[string]any{
				"id": "banner", "type": "shape", "shape": "rect",
				"transform": map[string]any{"x": 20.0, "y": 40.0, "scaleX": 1.0, "scaleY": 1.0, "rotation": 0.0},
				"size":      map[string]any{"width": 60.0, "height": 40.0},
				"fills":     []any{map[string]any{"type": "solid", "color": color(1, 0, 0)}},
			}},
		}},
	}

	data, err := renderTemplateOverlay(file, nil)
	if err != nil {
		t.Fatalf("renderTemplateOverlay: %v", err)
	}
	image, err := png.Decode(bytes.NewReader(data))
	if err != nil {
		t.Fatalf("decode overlay PNG: %v", err)
	}
	if image.Bounds().Dx() != 25 || image.Bounds().Dy() != 50 {
		t.Fatalf("overlay dimensions = %dx%d, want 25x50", image.Bounds().Dx(), image.Bounds().Dy())
	}
	_, _, _, alpha := image.At(0, 0).RGBA()
	if alpha != 0 {
		t.Fatalf("overlay background alpha = %d, want 0", alpha)
	}
	red, green, blue, alpha := image.At(12, 15).RGBA()
	if alpha == 0 || red <= green || red <= blue {
		t.Fatalf("overlay element = RGBA(%d, %d, %d, %d), want visible red template element", red, green, blue, alpha)
	}
}

func TestTemplatePreviewAPIKeyRouteRequiresExportScope(t *testing.T) {
	route, designID, ok := matchAPIKeyRoute(http.MethodGet, "/api/v1/templates/template-id/render.png")
	if !ok {
		t.Fatal("template preview route is not available to API keys")
	}
	if route.scope != apikeys.ScopeExport || designID != "" {
		t.Fatalf("template preview route = scope %q design %q", route.scope, designID)
	}
}

func TestTemplateOverlayAPIKeyRouteRequiresExportScope(t *testing.T) {
	route, designID, ok := matchAPIKeyRoute(http.MethodGet, "/api/v1/templates/template-id/render-overlay.png")
	if !ok {
		t.Fatal("template overlay route is not available to API keys")
	}
	if route.scope != apikeys.ScopeExport || designID != "" {
		t.Fatalf("template overlay route = scope %q design %q", route.scope, designID)
	}
}

func TestTemplateBackgroundPreviewAPIKeyRouteRequiresExportScope(t *testing.T) {
	route, designID, ok := matchAPIKeyRoute(http.MethodPost, "/api/v1/templates/template-id/preview.png")
	if !ok {
		t.Fatal("template background preview route is not available to API keys")
	}
	if route.scope != apikeys.ScopeExport || designID != "" {
		t.Fatalf("template background preview route = scope %q design %q", route.scope, designID)
	}
}

func TestTemplateCatalogIsPublicAndNeedsNoWorkspaceID(t *testing.T) {
	service := templates.NewService(publicCatalogDB{}, nil, nil)
	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodGet, "/api/v1/templates/catalog", nil)

	templatesCatalogHandler(service).ServeHTTP(recorder, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("status = %d body=%s", recorder.Code, recorder.Body.String())
	}
	var response struct {
		Categories []templates.Category `json:"categories"`
	}
	if err := json.NewDecoder(recorder.Body).Decode(&response); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if len(response.Categories) != 1 || response.Categories[0].Name != "内容报价" || response.Categories[0].Templates == nil {
		t.Fatalf("response = %+v", response)
	}
}
