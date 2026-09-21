package httpapi

import (
	"bytes"
	"errors"
	"io"
	"mime/multipart"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"

	"hycanvas/backend/internal/accounts"
	"hycanvas/backend/internal/fontlibrary"
)

func mountFonts(api chi.Router, library *fontlibrary.Service, acct *accounts.Service) {
	api.Group(func(r chi.Router) {
		r.Use(requireAuth(acct))
		r.Get("/fonts", listFontsHandler(library))
		r.Post("/fonts", uploadFontHandler(library))
	})
	// Font files belong to a public, server-wide catalogue. Keeping content
	// delivery public also lets signed share views load the exact design face.
	api.Get("/fonts/{id}/content", fontContentHandler(library))
	api.Head("/fonts/{id}/content", fontContentHandler(library))
}

func fontsProblem(w http.ResponseWriter, r *http.Request, err error) {
	switch {
	case errors.Is(err, fontlibrary.ErrBadRequest):
		problemWithCode(w, r, http.StatusBadRequest, "Bad Request", "upload a valid TTF or OTF font for the Xiaohongshu zone", "font_invalid")
	case errors.Is(err, fontlibrary.ErrTooLarge):
		problemWithCode(w, r, http.StatusRequestEntityTooLarge, "Payload Too Large", err.Error(), "font_too_large")
	case errors.Is(err, fontlibrary.ErrNotFound):
		problemWithCode(w, r, http.StatusNotFound, "Not Found", "font not found", "font_not_found")
	default:
		problemWithCode(w, r, http.StatusInternalServerError, "Internal Server Error", "font request failed", "font_failed")
	}
}

func listFontsHandler(library *fontlibrary.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		fonts, err := library.List(r.Context(), r.URL.Query().Get("zone"))
		if err != nil {
			fontsProblem(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, fonts)
	}
}

func uploadFontHandler(library *fontlibrary.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		r.Body = http.MaxBytesReader(w, r.Body, fontlibrary.MaxFontBytes+(1<<20))
		if err := r.ParseMultipartForm(4 << 20); err != nil {
			var maxErr *http.MaxBytesError
			if errors.As(err, &maxErr) || errors.Is(err, multipart.ErrMessageTooLarge) {
				fontsProblem(w, r, fontlibrary.ErrTooLarge)
				return
			}
			fontsProblem(w, r, fontlibrary.ErrBadRequest)
			return
		}
		file, _, err := r.FormFile("file")
		if err != nil {
			fontsProblem(w, r, fontlibrary.ErrBadRequest)
			return
		}
		defer file.Close()
		data, err := io.ReadAll(io.LimitReader(file, fontlibrary.MaxFontBytes+1))
		if err != nil {
			fontsProblem(w, r, fontlibrary.ErrBadRequest)
			return
		}
		if len(data) > fontlibrary.MaxFontBytes {
			fontsProblem(w, r, fontlibrary.ErrTooLarge)
			return
		}
		font, err := library.Upload(r.Context(), userFrom(r.Context()).ID, r.FormValue("zone"), data)
		if err != nil {
			fontsProblem(w, r, err)
			return
		}
		writeJSON(w, http.StatusCreated, font)
	}
}

func fontContentHandler(library *fontlibrary.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		data, font, err := library.Content(r.Context(), chi.URLParam(r, "id"))
		if err != nil {
			fontsProblem(w, r, err)
			return
		}
		w.Header().Set("Content-Type", font.MimeType)
		w.Header().Set("Cache-Control", "public, max-age=31536000, immutable")
		http.ServeContent(w, r, font.Family+"."+font.Format, time.Unix(0, 0), bytes.NewReader(data))
	}
}
