type SelectedFilesListProps = {
  files: File[];
  onRemove?: (index: number) => void;
};

export function SelectedFilesList({ files, onRemove }: SelectedFilesListProps) {
  if (!files.length) {
    return null;
  }
  return (
    <div className="selected-files">
      <p className="helper">
        Selected files ({files.length})
      </p>
      <ul className="selected-files-list">
        {files.map((file, index) => (
          <li key={`${file.name}-${file.size}-${index}`} className="selected-file-item">
            <span className="selected-file-name" title={file.name}>
              {file.name}
            </span>
            <span className="selected-file-size">{Math.ceil(file.size / 1024)} KB</span>
            {onRemove ? (
              <button
                type="button"
                className="secondary-btn selected-file-remove"
                onClick={() => onRemove(index)}
                aria-label={`Remove ${file.name}`}
              >
                Remove
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
