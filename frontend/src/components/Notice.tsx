type NoticeProps = {
  type: "error" | "success" | "info";
  message: string;
};

export function Notice({ type, message }: NoticeProps) {
  const role = type === "error" ? "alert" : "status";
  const ariaLive = type === "error" ? "assertive" : "polite";
  return (
    <div className={`notice ${type}`} role={role} aria-live={ariaLive} aria-atomic="true">
      {message}
    </div>
  );
}
