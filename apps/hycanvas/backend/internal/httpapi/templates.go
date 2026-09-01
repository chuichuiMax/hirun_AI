package httpapi

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"

	"hycanvas/backend/internal/accounts"
	"hycanvas/backend/internal/templates"
)

// mountTemplates attaches the templates catalog + apply + collections (doc 14).
// All JWT-guarded; visibility scope is enforced in the service. Static segments
// (collections) are registered before the {id} param routes.
func mountTemplates(api chi.Router, tm *templates.Service, acct *accounts.Service) {
	api.Group(func(r chi.Router) {
		r.Use(requireAuth(acct))
		r.Get("/templates", templatesListHandler(tm))
		r.Post("/templates", templatesSaveHandler(tm))
		r.Get("/templates/collections", templatesListCollectionsHandler(tm))
		r.Post("/templates/collections", templatesCreateCollectionHandler(tm))
		r.Delete("/templates/collections/{id}", templatesDeleteCollectionHandler(tm))
		r.Get("/templates/{id}", templatesGetHandler(tm))
		r.Get("/templates/{id}/file", templatesFileHandler(tm))
		r.Get("/templates/{id}/fillable-fields", templatesFillableHandler(tm))
		r.Post("/templates/{id}/apply", templatesApplyHandler(tm))
		r.Post("/templates/{id}/instantiate", templatesInstantiateHandler(tm))
		r.Post("/templates/{id}/collection", templatesAssignCollectionHandler(tm))
	})
}

func templatesProblem(w http.ResponseWriter, r *http.Request, err error) {
	switch {
	case errors.Is(err, templates.ErrForbidden):
		problemWithCode(w, r, http.StatusForbidden, "Forbidden", "you do not have permission for this action", "forbidden_action")
	case errors.Is(err, templates.ErrNotFound):
		problemWithCode(w, r, http.StatusNotFound, "Not Found", "template not found", "template_not_found")
	case errors.Is(err, templates.ErrBadRequest):
		problemWithCode(w, r, http.StatusBadRequest, "Bad Request", "invalid request", "invalid_request")
	default:
		problemWithCode(w, r, http.StatusInternalServerError, "Internal Server Error", "request failed", "request_failed")
	}
}

func templatesListHandler(tm *templates.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		query := templates.TemplateQuery{Text: q.Get("q"), Color: q.Get("color")}
		if c := q.Get("category"); c != "" {
			query.Categories = strings.Split(c, ",")
		}
		u := userFrom(r.Context())
		workspaceID := q.Get("workspaceId")
		if key := apiKeyFrom(r.Context()); key != nil {
			workspaceID = key.WorkspaceID
		}
		list, err := tm.List(r.Context(), u.ID, query, workspaceID, q.Get("collection"))
		if err != nil {
			templatesProblem(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, list)
	}
}

func templatesSaveHandler(tm *templates.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			WorkspaceID  string         `json:"workspaceId"`
			DesignID     string         `json:"designId"`
			File         map[string]any `json:"file"`
			Title        string         `json:"title"`
			Category     string         `json:"category"`
			Tags         []string       `json:"tags"`
			Thumbnail    string         `json:"thumbnail"`
			Visibility   string         `json:"visibility"`
			CollectionID string         `json:"collectionId"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			problemWithCode(w, r, http.StatusBadRequest, "Bad Request", "invalid body", "invalid_body")
			return
		}
		u := userFrom(r.Context())
		t, err := tm.SaveAsTemplate(r.Context(), u.ID, templates.SaveInput{
			WorkspaceID: body.WorkspaceID, DesignID: body.DesignID, File: body.File, Title: body.Title,
			Category: body.Category, Tags: body.Tags, Thumbnail: body.Thumbnail,
			Visibility: body.Visibility, CollectionID: body.CollectionID,
		})
		if err != nil {
			templatesProblem(w, r, err)
			return
		}
		writeJSON(w, http.StatusCreated, t)
	}
}

func templatesGetHandler(tm *templates.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		u := userFrom(r.Context())
		t, err := tm.Get(r.Context(), u.ID, chi.URLParam(r, "id"))
		if err != nil {
			templatesProblem(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, t)
	}
}

func templatesFileHandler(tm *templates.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		u := userFrom(r.Context())
		f, err := tm.GetFile(r.Context(), u.ID, chi.URLParam(r, "id"))
		if err != nil {
			templatesProblem(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, f)
	}
}

func templatesFillableHandler(tm *templates.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		u := userFrom(r.Context())
		fields, err := tm.GetFillableFields(r.Context(), u.ID, chi.URLParam(r, "id"))
		if err != nil {
			templatesProblem(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, fields)
	}
}

func templatesApplyHandler(tm *templates.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			WorkspaceID string `json:"workspaceId"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil || body.WorkspaceID == "" {
			problemWithCode(w, r, http.StatusBadRequest, "Bad Request", "missing workspaceId", "missing_workspaceid")
			return
		}
		u := userFrom(r.Context())
		designID, err := tm.Apply(r.Context(), u.ID, chi.URLParam(r, "id"), body.WorkspaceID)
		if err != nil {
			templatesProblem(w, r, err)
			return
		}
		writeJSON(w, http.StatusCreated, map[string]string{"designId": designID})
	}
}

func templatesInstantiateHandler(tm *templates.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			WorkspaceID string            `json:"workspaceId"`
			Title       string            `json:"title"`
			Fields      map[string]string `json:"fields"`
			Background  *struct {
				Filename    string `json:"filename"`
				ContentType string `json:"contentType"`
				DataBase64  string `json:"dataBase64"`
			} `json:"backgroundImage"`
			Images map[string]struct {
				Filename    string `json:"filename"`
				ContentType string `json:"contentType"`
				DataBase64  string `json:"dataBase64"`
			} `json:"images"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			problemWithCode(w, r, http.StatusBadRequest, "Bad Request", "invalid body", "invalid_body")
			return
		}
		if key := apiKeyFrom(r.Context()); key != nil && body.WorkspaceID != key.WorkspaceID {
			problemWithCode(w, r, http.StatusForbidden, "Forbidden", "the API key cannot create designs in this workspace", "api_key_workspace_mismatch")
			return
		}
		u := userFrom(r.Context())
		images := make(map[string]templates.InstantiateImage, len(body.Images))
		for label, image := range body.Images {
			images[label] = templates.InstantiateImage{
				Filename: image.Filename, ContentType: image.ContentType, DataBase64: image.DataBase64,
			}
		}
		var background *templates.InstantiateImage
		if body.Background != nil {
			background = &templates.InstantiateImage{
				Filename: body.Background.Filename, ContentType: body.Background.ContentType, DataBase64: body.Background.DataBase64,
			}
		}
		designID, err := tm.Instantiate(r.Context(), u.ID, chi.URLParam(r, "id"), templates.InstantiateInput{
			WorkspaceID: body.WorkspaceID,
			Title:       body.Title,
			Fields:      body.Fields,
			Images:      images,
			Background:  background,
		})
		if err != nil {
			templatesProblem(w, r, err)
			return
		}
		writeJSON(w, http.StatusCreated, map[string]string{"designId": designID})
	}
}

func templatesListCollectionsHandler(tm *templates.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		u := userFrom(r.Context())
		cols, err := tm.ListCollections(r.Context(), u.ID, r.URL.Query().Get("workspaceId"))
		if err != nil {
			templatesProblem(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, cols)
	}
}

func templatesCreateCollectionHandler(tm *templates.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			WorkspaceID string `json:"workspaceId"`
			Name        string `json:"name"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			problemWithCode(w, r, http.StatusBadRequest, "Bad Request", "invalid body", "invalid_body")
			return
		}
		u := userFrom(r.Context())
		col, err := tm.CreateCollection(r.Context(), u.ID, body.WorkspaceID, body.Name)
		if err != nil {
			templatesProblem(w, r, err)
			return
		}
		writeJSON(w, http.StatusCreated, col)
	}
}

func templatesDeleteCollectionHandler(tm *templates.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		u := userFrom(r.Context())
		if err := tm.DeleteCollection(r.Context(), u.ID, chi.URLParam(r, "id")); err != nil {
			templatesProblem(w, r, err)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	}
}

func templatesAssignCollectionHandler(tm *templates.Service) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			CollectionID string `json:"collectionId"`
		}
		_ = json.NewDecoder(r.Body).Decode(&body)
		u := userFrom(r.Context())
		t, err := tm.AssignCollection(r.Context(), u.ID, chi.URLParam(r, "id"), body.CollectionID)
		if err != nil {
			templatesProblem(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, t)
	}
}
