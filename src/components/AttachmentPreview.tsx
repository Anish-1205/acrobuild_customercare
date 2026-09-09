import { useEffect, useRef } from "react";

export function AttachmentPreview({ src, alt, onClose }: { src: string; alt: string; onClose: () => void }) {
  const closeButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    closeButton.current?.focus();
    return () => previous?.focus();
  }, []);
  return (
    <div className="support-image-lightbox" role="dialog" aria-modal="true" aria-label="Attachment preview"
      onClick={onClose} onKeyDown={event => {
        if (event.key === "Escape") onClose();
        if (event.key === "Tab") { event.preventDefault(); closeButton.current?.focus(); }
      }}>
      <div className="support-image-lightbox-frame" onClick={event => event.stopPropagation()}>
        <button ref={closeButton} aria-label="Close image preview" className="support-image-lightbox-close" onClick={onClose} type="button">Close</button>
        <img alt={alt} className="support-image-lightbox-image" src={src} />
        <div className="support-image-lightbox-caption">{alt}</div>
      </div>
    </div>
  );
}
