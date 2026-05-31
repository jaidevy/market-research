export function CrudSubHeader({ title, meta, children }) {
  return (
    <div className="crud-subheader">
      <div className="crud-subheader-head">
        <h2 className="screen-title">{title}</h2>
        <span className="agent-count">{meta}</span>
      </div>
      <div className="crud-subheader-controls tool-toolbar">
        {children}
      </div>
    </div>
  );
}
