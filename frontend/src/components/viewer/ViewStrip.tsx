import { useEffect, useState } from "react";
import { api, type ImageSummary } from "../../api/client";
import { Icon } from "../icons";
import { cx } from "../ui";

export interface StudyView {
  id: string;
  label: string;
  caption: string;
  image: ImageSummary | null;
}

export function ViewStrip({
  views,
  activeId,
  onSelect,
  onPrev,
  onNext,
}: {
  views: StudyView[];
  activeId: string | null;
  onSelect: (imageId: string) => void;
  onPrev: () => void;
  onNext: () => void;
}) {
  const index = views.findIndex((view) => view.id === activeId);
  const many = views.filter((view) => view.image).length > 1;

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="text-xs font-medium text-muted">
          Views{" "}
          {index >= 0 ? (
            <span className="font-mono text-xs normal-case tracking-normal">
              {index + 1}/{views.length}
            </span>
          ) : null}
        </h2>
        {many ? (
          <div className="flex gap-1">
            <button
              type="button"
              onClick={onPrev}
              aria-label="Previous view"
              className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-2 hover:text-ink"
            >
              <Icon name="chevron-left" size={16} />
            </button>
            <button
              type="button"
              onClick={onNext}
              aria-label="Next view"
              className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-2 hover:text-ink"
            >
              <Icon name="chevron-right" size={16} />
            </button>
          </div>
        ) : null}
      </div>
      <ul className="grid max-h-80 grid-cols-2 gap-2 overflow-y-auto pr-0.5">
        {views.map((view) => (
          <li key={view.id || view.label}>
            <button
              type="button"
              disabled={!view.image}
              aria-pressed={view.id === activeId}
              onClick={() => view.image && onSelect(view.image.id)}
              className={cx(
                "group w-full overflow-hidden rounded-lg text-left transition-colors duration-150 ease-out",
                view.id === activeId
                  ? "bg-petrol-soft ring-1 ring-petrol"
                  : "bg-surface-2 hover:bg-surface-2/70",
                !view.image && "opacity-50",
              )}
            >
              <ViewThumbnail image={view.image} label={view.label} />
              <span className="flex items-center justify-between gap-1 px-2 py-1.5">
                <span className="truncate text-xs font-medium text-ink">{view.label}</span>
                {view.caption.toLowerCase() !== view.label.toLowerCase() ? (
                  <span className="truncate text-xs text-muted">{view.caption}</span>
                ) : null}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ViewThumbnail({ image, label }: { image: ImageSummary | null; label: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!image) return;
    let revoked = false;
    let objectUrl: string | null = null;
    setFailed(false);
    setUrl(null);
    api
      .preview(image.id)
      .then((buffer) => {
        if (revoked) return;
        objectUrl = URL.createObjectURL(new Blob([buffer], { type: "image/png" }));
        setUrl(objectUrl);
      })
      .catch(() => setFailed(true));
    return () => {
      revoked = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [image?.id]);

  if (!image) {
    return (
      <span className="flex aspect-[4/3] w-full items-center justify-center bg-surface-2 text-muted">
        <Icon name="image" size={18} />
      </span>
    );
  }

  return (
    <span className="relative flex aspect-[4/3] w-full items-center justify-center overflow-hidden bg-viewer">
      {url && !failed ? (
        <img src={url} alt={`${label} preview`} className="h-full w-full object-contain" />
      ) : (
        <span className="text-xs text-viewer-muted">{failed ? "No preview" : label}</span>
      )}
    </span>
  );
}
