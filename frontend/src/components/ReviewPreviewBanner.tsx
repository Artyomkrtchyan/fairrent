export function ReviewPreviewBanner() {
  return (
    <div
      role="note"
      className="mb-6 rounded-xl border border-above/40 bg-warn-banner p-4 text-sm text-warn-banner-foreground"
    >
      <strong>Preview only — deferred feature.</strong> The reviewer workspace is not live. There is
      no sign-in, and decision forms are disabled. Cases shown are synthetic.
    </div>
  );
}
