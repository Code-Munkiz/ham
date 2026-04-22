/** Defense-in-depth: signed-in Clerk user blocked by HAM email/domain allowlist (`HAM_EMAIL_RESTRICTION`). */
export function HamDeploymentRestrictedBanner({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <div
      role="status"
      className="shrink-0 px-4 py-2 text-xs border-b border-amber-500/40 bg-amber-500/10 text-amber-950 dark:text-amber-100"
    >
      <span className="font-semibold">Restricted access.</span> You are signed in, but this account is not approved
      for this Ham deployment (email/domain allowlist). Contact an administrator or use an allowed identity. Clerk
      Dashboard restrictions remain the primary gate; this message is from Ham defense-in-depth.
    </div>
  );
}
