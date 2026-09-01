package templates

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
)

type InstantiateImage struct {
	Filename    string
	ContentType string
	DataBase64  string
}

// InstantiateInput describes one automation-created design. Fields are keyed
// by the human-readable labels declared in the template's fillableFields.
type InstantiateInput struct {
	WorkspaceID string
	Title       string
	Fields      map[string]string
	Images      map[string]InstantiateImage
}

// Instantiate fills a template's declared text fields and creates a decoupled
// design in the requested workspace.
func (s *Service) Instantiate(ctx context.Context, userID, templateID string, in InstantiateInput) (string, error) {
	if in.WorkspaceID == "" || len(in.Fields) == 0 {
		return "", ErrBadRequest
	}
	if err := s.access.AssertMember(ctx, userID, in.WorkspaceID, "member"); err != nil {
		return "", ErrForbidden
	}

	var file map[string]any
	var template Template
	if seed, ok := findSeed(templateID); ok {
		_ = json.Unmarshal(seed.File, &file)
		template = seed.toTemplate()
	} else {
		row, err := s.getRow(ctx, templateID)
		if err != nil {
			return "", err
		}
		if !s.canSee(ctx, userID, row) {
			return "", ErrNotFound
		}
		_ = json.Unmarshal(row.File, &file)
		template = rowToTemplate(row)
	}

	if err := fillTextFields(file, template.FillableFields, in.Fields); err != nil {
		return "", err
	}
	if err := fillImageFields(file, template.FillableFields, in.Images); err != nil {
		return "", err
	}
	applied, _ := deepCopyDesign(file)
	title := strings.TrimSpace(in.Title)
	if title == "" {
		title = template.Title
	}
	return s.persist.CreateDesign(ctx, in.WorkspaceID, title, applied, &userID)
}

func fillImageFields(file map[string]any, declarations []any, values map[string]InstantiateImage) error {
	fieldNodes := make(map[string]string, len(declarations))
	for _, raw := range declarations {
		field := asObj(raw)
		if asStr(field["kind"]) == "image" {
			fieldNodes[asStr(field["label"])] = asStr(field["nodeId"])
		}
	}
	remaining := make(map[string]InstantiateImage, len(values))
	for label, value := range values {
		if fieldNodes[label] == "" || value.DataBase64 == "" || !strings.HasPrefix(value.ContentType, "image/") {
			return ErrBadRequest
		}
		remaining[fieldNodes[label]] = value
	}
	for _, pageRaw := range asArr(file["pages"]) {
		for _, root := range asArr(asObj(pageRaw)["children"]) {
			visitTree(asObj(root), func(node map[string]any) {
				value, ok := remaining[asStr(node["id"])]
				if !ok {
					return
				}
				for key := range node {
					if key != "id" && key != "transform" && key != "size" && key != "opacity" && key != "blendMode" {
						delete(node, key)
					}
				}
				node["type"] = "image"
				node["fit"] = "cover"
				node["source"] = map[string]any{"assetId": "", "naturalWidth": 0, "naturalHeight": 0}
				node["src"] = fmt.Sprintf("data:%s;base64,%s", value.ContentType, value.DataBase64)
				delete(remaining, asStr(node["id"]))
			})
		}
	}
	if len(remaining) > 0 {
		return ErrBadRequest
	}
	return nil
}

func fillTextFields(file map[string]any, declarations []any, values map[string]string) error {
	fieldNodes := make(map[string]string, len(declarations))
	for _, raw := range declarations {
		field := asObj(raw)
		if asStr(field["kind"]) == "text" {
			fieldNodes[asStr(field["label"])] = asStr(field["nodeId"])
		}
	}
	for label := range values {
		if fieldNodes[label] == "" {
			return ErrBadRequest
		}
	}

	remaining := make(map[string]string, len(values))
	for label, value := range values {
		remaining[fieldNodes[label]] = value
	}
	for _, pageRaw := range asArr(file["pages"]) {
		for _, root := range asArr(asObj(pageRaw)["children"]) {
			visitTree(asObj(root), func(node map[string]any) {
				value, ok := remaining[asStr(node["id"])]
				if !ok || asStr(node["type"]) != "text" {
					return
				}
				paragraphs := asArr(node["content"])
				if len(paragraphs) == 0 {
					return
				}
				first := asObj(paragraphs[0])
				runs := asArr(first["runs"])
				if len(runs) == 0 {
					return
				}
				asObj(runs[0])["text"] = value
				first["runs"] = runs[:1]
				node["content"] = []any{first}
				delete(remaining, asStr(node["id"]))
			})
		}
	}
	if len(remaining) > 0 {
		return ErrBadRequest
	}
	return nil
}
