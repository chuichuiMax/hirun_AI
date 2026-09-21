package httpapi

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"hycanvas/backend/internal/accounts"
	"hycanvas/backend/internal/fontlibrary"
	"hycanvas/backend/internal/storage"
)

func TestPublicFontSurface_DB(t *testing.T) {
	dsn := os.Getenv("DATABASE_URL")
	if dsn == "" {
		t.Skip("DATABASE_URL not set; skipping DB integration test")
	}
	ctx := context.Background()
	conn, err := pgx.Connect(ctx, stripSchemaParam(dsn))
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	defer conn.Close(ctx)
	tx, err := conn.Begin(ctx)
	if err != nil {
		t.Fatalf("begin: %v", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	acct := accounts.NewService(tx, "test-jwt-secret")
	_, _, uploaderTokens, err := acct.Signup(ctx, "font-uploader+"+uuid.NewString()+"@example.com", "a-strong-password", "Uploader")
	if err != nil {
		t.Fatalf("signup uploader: %v", err)
	}
	_, _, readerTokens, err := acct.Signup(ctx, "font-reader+"+uuid.NewString()+"@example.com", "a-strong-password", "Reader")
	if err != nil {
		t.Fatalf("signup reader: %v", err)
	}
	store, err := storage.NewLocal(t.TempDir())
	if err != nil {
		t.Fatalf("local storage: %v", err)
	}
	library := fontlibrary.NewService(tx, store, nil)
	before, err := library.List(ctx, fontlibrary.ZoneXiaohongshu)
	if err != nil {
		t.Fatalf("list existing fonts: %v", err)
	}

	router := chi.NewRouter()
	router.Route("/api/v1", func(api chi.Router) { mountFonts(api, library, acct) })
	server := httptest.NewServer(router)
	defer server.Close()

	fontBytes, err := os.ReadFile("../render/fonts/LiberationSans-Regular.ttf")
	if err != nil {
		t.Fatalf("read fixture font: %v", err)
	}
	upload := func(token string) *http.Response {
		var body bytes.Buffer
		writer := multipart.NewWriter(&body)
		if err := writer.WriteField("zone", fontlibrary.ZoneXiaohongshu); err != nil {
			t.Fatalf("write zone: %v", err)
		}
		part, err := writer.CreateFormFile("file", "LiberationSans-Regular.ttf")
		if err != nil {
			t.Fatalf("create font part: %v", err)
		}
		if _, err := part.Write(fontBytes); err != nil {
			t.Fatalf("write font: %v", err)
		}
		if err := writer.Close(); err != nil {
			t.Fatalf("close multipart: %v", err)
		}
		req, _ := http.NewRequest(http.MethodPost, server.URL+"/api/v1/fonts", &body)
		req.Header.Set("Authorization", "Bearer "+token)
		req.Header.Set("Content-Type", writer.FormDataContentType())
		res, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatalf("upload font: %v", err)
		}
		return res
	}

	res := upload(uploaderTokens.Access)
	if res.StatusCode != http.StatusCreated {
		body, _ := io.ReadAll(res.Body)
		res.Body.Close()
		t.Fatalf("upload status = %d, body = %s", res.StatusCode, body)
	}
	var uploaded fontlibrary.Font
	if err := json.NewDecoder(res.Body).Decode(&uploaded); err != nil {
		t.Fatalf("decode upload: %v", err)
	}
	res.Body.Close()
	if uploaded.Zone != fontlibrary.ZoneXiaohongshu || uploaded.Family != "Liberation Sans" {
		t.Fatalf("unexpected uploaded font: %+v", uploaded)
	}

	listReq, _ := http.NewRequest(http.MethodGet, server.URL+"/api/v1/fonts?zone=xiaohongshu", nil)
	listReq.Header.Set("Authorization", "Bearer "+readerTokens.Access)
	res, err = http.DefaultClient.Do(listReq)
	if err != nil {
		t.Fatalf("list as another user: %v", err)
	}
	var listed []fontlibrary.Font
	if err := json.NewDecoder(res.Body).Decode(&listed); err != nil {
		t.Fatalf("decode list: %v", err)
	}
	res.Body.Close()
	found := false
	for _, font := range listed {
		if font.ID == uploaded.ID {
			found = true
			break
		}
	}
	if res.StatusCode != http.StatusOK || len(listed) != len(before)+1 || !found {
		t.Fatalf("another user did not see the uploaded font: status=%d fonts=%+v", res.StatusCode, listed)
	}

	res = upload(readerTokens.Access)
	if res.StatusCode != http.StatusCreated {
		t.Fatalf("duplicate upload status = %d", res.StatusCode)
	}
	var duplicate fontlibrary.Font
	if err := json.NewDecoder(res.Body).Decode(&duplicate); err != nil {
		t.Fatalf("decode duplicate: %v", err)
	}
	res.Body.Close()
	if duplicate.ID != uploaded.ID {
		t.Fatalf("duplicate upload created a second record: first=%s second=%s", uploaded.ID, duplicate.ID)
	}

	headReq, _ := http.NewRequest(http.MethodHead, server.URL+uploaded.URL, nil)
	res, err = http.DefaultClient.Do(headReq)
	if err != nil {
		t.Fatalf("head public font: %v", err)
	}
	res.Body.Close()
	if res.StatusCode != http.StatusOK || res.ContentLength != int64(len(fontBytes)) {
		t.Fatalf("public font content: status=%d length=%d", res.StatusCode, res.ContentLength)
	}

	res, err = http.Get(server.URL + "/api/v1/fonts?zone=xiaohongshu")
	if err != nil {
		t.Fatalf("unauthenticated list: %v", err)
	}
	res.Body.Close()
	if res.StatusCode != http.StatusUnauthorized {
		t.Fatalf("unauthenticated list status = %d", res.StatusCode)
	}
}
