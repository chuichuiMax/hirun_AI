package fontlibrary

import (
	"context"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
)

type DBTX interface {
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
	Query(ctx context.Context, sql string, args ...any) (pgx.Rows, error)
	Exec(ctx context.Context, sql string, args ...any) (pgconn.CommandTag, error)
}

type fontRow struct {
	ID         string
	Zone       string
	Family     string
	Style      string
	Weight     int
	Format     string
	MimeType   string
	StorageKey string
	SHA256     string
	ByteSize   int64
	Variable   bool
	UploadedBy *string
	CreatedAt  time.Time
}

const fontCols = `id,zone,family,style,weight,format,"mime_type","storage_key",sha256,"byte_size",variable,"uploaded_by_id","created_at"`

func scanFont(row pgx.Row) (fontRow, error) {
	var font fontRow
	err := row.Scan(
		&font.ID, &font.Zone, &font.Family, &font.Style, &font.Weight,
		&font.Format, &font.MimeType, &font.StorageKey, &font.SHA256,
		&font.ByteSize, &font.Variable, &font.UploadedBy, &font.CreatedAt,
	)
	return font, err
}

func (s *Service) upsert(ctx context.Context, font fontRow) (fontRow, error) {
	const query = `INSERT INTO "public_fonts"
		(id,zone,family,style,weight,format,"mime_type","storage_key",sha256,"byte_size",variable,"uploaded_by_id","updated_at")
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,now())
		ON CONFLICT (zone, sha256) DO UPDATE SET
			family = EXCLUDED.family,
			style = EXCLUDED.style,
			weight = EXCLUDED.weight,
			format = EXCLUDED.format,
			"mime_type" = EXCLUDED."mime_type",
			"storage_key" = EXCLUDED."storage_key",
			"byte_size" = EXCLUDED."byte_size",
			variable = EXCLUDED.variable,
			"updated_at" = now()
		RETURNING ` + fontCols
	return scanFont(s.db.QueryRow(ctx, query,
		font.ID, font.Zone, font.Family, font.Style, font.Weight, font.Format,
		font.MimeType, font.StorageKey, font.SHA256, font.ByteSize,
		font.Variable, font.UploadedBy,
	))
}

func (s *Service) get(ctx context.Context, id string) (fontRow, error) {
	font, err := scanFont(s.db.QueryRow(ctx, `SELECT `+fontCols+` FROM "public_fonts" WHERE id = $1`, id))
	if errors.Is(err, pgx.ErrNoRows) {
		return fontRow{}, ErrNotFound
	}
	return font, err
}

func (s *Service) list(ctx context.Context, zone string) ([]fontRow, error) {
	rows, err := s.db.Query(ctx, `SELECT `+fontCols+` FROM "public_fonts" WHERE zone = $1 ORDER BY lower(family), weight, lower(style), "created_at"`, zone)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	fonts := []fontRow{}
	for rows.Next() {
		font, scanErr := scanFont(rows)
		if scanErr != nil {
			return nil, scanErr
		}
		fonts = append(fonts, font)
	}
	return fonts, rows.Err()
}
