// Package fontlibrary owns the instance-wide font catalogue used exclusively by
// the Xiaohongshu template zone. Metadata lives in Postgres and font bytes live
// in the configured storage driver, so a browser cache or container rebuild is
// never the source of truth.
package fontlibrary

import (
	"context"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"unicode"
	"unicode/utf16"

	"github.com/google/uuid"
	"golang.org/x/image/font/sfnt"

	"hycanvas/backend/internal/storage"
)

const (
	ZoneXiaohongshu = "xiaohongshu"
	MaxFontBytes    = 128 << 20
)

var (
	ErrBadRequest = errors.New("invalid font upload")
	ErrNotFound   = errors.New("font not found")
	ErrTooLarge   = errors.New("font file is too large")
)

// RegisterFunc connects retained library fonts to the server-side renderer.
type RegisterFunc func(family string, weight int, data []byte) error

type Service struct {
	db       DBTX
	storage  storage.Driver
	register RegisterFunc
}

func NewService(db DBTX, store storage.Driver, register RegisterFunc) *Service {
	return &Service{db: db, storage: store, register: register}
}

// Font is the public catalogue representation. URL contains only a stable
// content endpoint; the binary is never inlined into design JSON.
type Font struct {
	ID         string `json:"id"`
	Zone       string `json:"zone"`
	Family     string `json:"family"`
	Style      string `json:"style"`
	Weight     int    `json:"weight"`
	Format     string `json:"format"`
	MimeType   string `json:"mimeType"`
	ByteSize   int64  `json:"byteSize"`
	SHA256     string `json:"sha256"`
	Variable   bool   `json:"variable"`
	URL        string `json:"url"`
	UploadedBy string `json:"uploadedBy,omitempty"`
	CreatedAt  string `json:"createdAt"`
}

func toFont(row fontRow) Font {
	uploader := ""
	if row.UploadedBy != nil {
		uploader = *row.UploadedBy
	}
	return Font{
		ID: row.ID, Zone: row.Zone, Family: row.Family, Style: row.Style,
		Weight: row.Weight, Format: row.Format, MimeType: row.MimeType,
		ByteSize: row.ByteSize, SHA256: row.SHA256, Variable: row.Variable,
		URL: "/api/v1/fonts/" + row.ID + "/content", UploadedBy: uploader,
		CreatedAt: row.CreatedAt.UTC().Format("2006-01-02T15:04:05.000Z07:00"),
	}
}

func validZone(zone string) bool { return zone == ZoneXiaohongshu }

// List returns the retained faces available to every signed-in user in zone.
func (s *Service) List(ctx context.Context, zone string) ([]Font, error) {
	if !validZone(zone) {
		return nil, ErrBadRequest
	}
	rows, err := s.list(ctx, zone)
	if err != nil {
		return nil, err
	}
	out := make([]Font, 0, len(rows))
	for _, row := range rows {
		out = append(out, toFont(row))
	}
	return out, nil
}

// Upload validates one TTF/OTF, reads its internal names, deduplicates it by
// content hash, persists it, and makes it immediately available to exports.
func (s *Service) Upload(ctx context.Context, userID, zone string, data []byte) (Font, error) {
	if !validZone(zone) || len(data) == 0 {
		return Font{}, ErrBadRequest
	}
	if len(data) > MaxFontBytes {
		return Font{}, ErrTooLarge
	}
	meta, err := inspectFont(data)
	if err != nil {
		return Font{}, ErrBadRequest
	}
	sum := sha256.Sum256(data)
	digest := hex.EncodeToString(sum[:])
	key := "fonts/" + zone + "/" + digest + "." + meta.Format
	if _, err := s.storage.Put(key, data); err != nil {
		return Font{}, err
	}
	var uploader *string
	if userID != "" {
		uploader = &userID
	}
	row, err := s.upsert(ctx, fontRow{
		ID: uuid.NewString(), Zone: zone, Family: meta.Family, Style: meta.Style,
		Weight: meta.Weight, Format: meta.Format, MimeType: meta.MimeType,
		StorageKey: key, SHA256: digest, ByteSize: int64(len(data)),
		Variable: meta.Variable, UploadedBy: uploader,
	})
	if err != nil {
		return Font{}, err
	}
	if s.register != nil {
		if err := s.register(row.Family, row.Weight, data); err != nil {
			return Font{}, fmt.Errorf("register font: %w", err)
		}
	}
	return toFont(row), nil
}

// Content returns persisted bytes and metadata for the public content route.
func (s *Service) Content(ctx context.Context, id string) ([]byte, Font, error) {
	row, err := s.get(ctx, id)
	if err != nil {
		return nil, Font{}, err
	}
	data, err := s.storage.Get(row.StorageKey)
	if err != nil {
		return nil, Font{}, err
	}
	if len(data) == 0 {
		return nil, Font{}, ErrNotFound
	}
	return data, toFont(row), nil
}

// LoadRegistered restores every retained face into the renderer at startup.
// A broken/missing font is reported but does not hide the rest of the library.
func (s *Service) LoadRegistered(ctx context.Context) (int, []error) {
	rows, err := s.list(ctx, ZoneXiaohongshu)
	if err != nil {
		return 0, []error{err}
	}
	count := 0
	var errs []error
	for _, row := range rows {
		data, getErr := s.storage.Get(row.StorageKey)
		if getErr != nil || len(data) == 0 {
			if getErr == nil {
				getErr = ErrNotFound
			}
			errs = append(errs, fmt.Errorf("%s: %w", row.ID, getErr))
			continue
		}
		if s.register != nil {
			if registerErr := s.register(row.Family, row.Weight, data); registerErr != nil {
				errs = append(errs, fmt.Errorf("%s: %w", row.ID, registerErr))
				continue
			}
		}
		count++
	}
	return count, errs
}

type fontMeta struct {
	Family   string
	Style    string
	Weight   int
	Format   string
	MimeType string
	Variable bool
}

func inspectFont(data []byte) (fontMeta, error) {
	if len(data) < 12 {
		return fontMeta{}, ErrBadRequest
	}
	format, mime := "", ""
	switch string(data[:4]) {
	case "OTTO":
		format, mime = "otf", "font/otf"
	case "\x00\x01\x00\x00", "true":
		format, mime = "ttf", "font/ttf"
	default:
		return fontMeta{}, ErrBadRequest
	}
	parsed, err := sfnt.Parse(data)
	if err != nil {
		return fontMeta{}, err
	}
	var buf sfnt.Buffer
	family := rawFontName(data, uint16(sfnt.NameIDTypographicFamily))
	if family == "" {
		family = fontName(parsed, &buf, sfnt.NameIDTypographicFamily)
	}
	if family == "" {
		family = rawFontName(data, uint16(sfnt.NameIDFamily))
	}
	if family == "" {
		family = fontName(parsed, &buf, sfnt.NameIDFamily)
	}
	style := rawFontName(data, uint16(sfnt.NameIDTypographicSubfamily))
	if style == "" {
		style = fontName(parsed, &buf, sfnt.NameIDTypographicSubfamily)
	}
	if style == "" {
		style = rawFontName(data, uint16(sfnt.NameIDSubfamily))
	}
	if style == "" {
		style = fontName(parsed, &buf, sfnt.NameIDSubfamily)
	}
	family = cleanName(family)
	style = cleanName(style)
	if family == "" {
		return fontMeta{}, ErrBadRequest
	}
	if style == "" {
		style = "Regular"
	}
	weight := styleWeight(style)
	variable := hasTable(data, "fvar")
	if variable {
		if defaultWeight, ok := variableWeight(data); ok {
			weight = defaultWeight
		}
	}
	return fontMeta{
		Family: family, Style: style, Weight: weight,
		Format: format, MimeType: mime, Variable: hasTable(data, "fvar"),
	}, nil
}

func fontName(font *sfnt.Font, buf *sfnt.Buffer, id sfnt.NameID) string {
	name, err := font.Name(buf, id)
	if err != nil {
		return ""
	}
	return name
}

func cleanName(value string) string {
	value = strings.TrimSpace(value)
	value = strings.Map(func(r rune) rune {
		if unicode.IsControl(r) {
			return -1
		}
		return r
	}, value)
	if len([]rune(value)) > 200 {
		value = string([]rune(value)[:200])
	}
	return strings.TrimSpace(value)
}

func styleWeight(style string) int {
	name := strings.ToLower(style)
	name = strings.NewReplacer(" ", "", "-", "", "_", "", "italic", "", "oblique", "").Replace(name)
	weights := []struct {
		tokens []string
		weight int
	}{
		{[]string{"thin", "hairline", "极细"}, 100},
		{[]string{"extralight", "ultralight", "特细"}, 200},
		{[]string{"light", "细体", "轻型", "细"}, 300},
		{[]string{"medium", "中等", "中号"}, 500},
		{[]string{"semibold", "demibold", "半粗"}, 600},
		{[]string{"extrabold", "ultrabold", "超粗"}, 800},
		{[]string{"black", "heavy", "超黑", "黑体"}, 900},
		{[]string{"bold", "粗体", "粗"}, 700},
	}
	for _, candidate := range weights {
		for _, token := range candidate.tokens {
			if strings.Contains(name, token) {
				return candidate.weight
			}
		}
	}
	return 400
}

// rawFontName reads Unicode/Windows name records directly. sfnt.Font.Name is a
// good general fallback, but some Chinese fonts place a legacy Mac-encoded name
// after their Unicode name; choosing that record produces mojibake such as
// "®®???". Prefer a UTF-16 Chinese record, then another UTF-16 record.
func rawFontName(data []byte, nameID uint16) string {
	table := tableBytes(data, "name")
	if len(table) < 6 {
		return ""
	}
	count := int(binary.BigEndian.Uint16(table[2:4]))
	stringsOffset := int(binary.BigEndian.Uint16(table[4:6]))
	if 6+count*12 > len(table) || stringsOffset > len(table) {
		return ""
	}
	best, bestScore := "", -1
	for i := 0; i < count; i++ {
		record := table[6+i*12 : 6+(i+1)*12]
		platform := binary.BigEndian.Uint16(record[0:2])
		language := binary.BigEndian.Uint16(record[4:6])
		if binary.BigEndian.Uint16(record[6:8]) != nameID || (platform != 0 && platform != 3) {
			continue
		}
		length := int(binary.BigEndian.Uint16(record[8:10]))
		offset := stringsOffset + int(binary.BigEndian.Uint16(record[10:12]))
		if length == 0 || length%2 != 0 || offset < 0 || offset+length > len(table) {
			continue
		}
		value := cleanName(decodeUTF16BE(table[offset : offset+length]))
		if value == "" {
			continue
		}
		score := 100
		if platform == 3 {
			score += 10
		}
		if language == 0x0804 || language == 0x0404 || language == 0x0c04 || language == 0x1004 {
			score += 20
		} else if language == 0x0409 {
			score += 5
		}
		if score > bestScore {
			best, bestScore = value, score
		}
	}
	return best
}

func decodeUTF16BE(data []byte) string {
	units := make([]uint16, len(data)/2)
	for i := range units {
		units[i] = binary.BigEndian.Uint16(data[i*2 : i*2+2])
	}
	return string(utf16.Decode(units))
}

func variableWeight(data []byte) (int, bool) {
	table := tableBytes(data, "fvar")
	if len(table) < 16 {
		return 0, false
	}
	axesOffset := int(binary.BigEndian.Uint16(table[4:6]))
	axisCount := int(binary.BigEndian.Uint16(table[8:10]))
	axisSize := int(binary.BigEndian.Uint16(table[10:12]))
	if axisSize < 20 || axesOffset < 0 || axesOffset+axisCount*axisSize > len(table) {
		return 0, false
	}
	for i := 0; i < axisCount; i++ {
		axis := table[axesOffset+i*axisSize : axesOffset+(i+1)*axisSize]
		if string(axis[:4]) != "wght" {
			continue
		}
		fixed := int32(binary.BigEndian.Uint32(axis[8:12]))
		weight := int(fixed >> 16)
		if weight >= 1 && weight <= 1000 {
			return weight, true
		}
	}
	return 0, false
}

// hasTable performs the small amount of sfnt directory parsing needed to mark
// variable fonts. Bounds are checked before every table-directory read.
func hasTable(data []byte, tag string) bool {
	return tableBytes(data, tag) != nil
}

func tableBytes(data []byte, tag string) []byte {
	if len(data) < 12 || len(tag) != 4 {
		return nil
	}
	n := int(data[4])<<8 | int(data[5])
	if n < 0 || 12+n*16 > len(data) {
		return nil
	}
	for offset := 12; offset < 12+n*16; offset += 16 {
		if string(data[offset:offset+4]) == tag {
			tableOffset := int(binary.BigEndian.Uint32(data[offset+8 : offset+12]))
			tableLength := int(binary.BigEndian.Uint32(data[offset+12 : offset+16]))
			if tableOffset < 0 || tableLength < 0 || tableOffset+tableLength > len(data) {
				return nil
			}
			return data[tableOffset : tableOffset+tableLength]
		}
	}
	return nil
}
