import { useState, type ReactNode } from "react";
import { apiMode } from "@/api/client";
import { useReviewerSession } from "@/lib/reviewer-session";

export function ReviewerSession({ children }: { children: ReactNode }) {
  const session = useReviewerSession();
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  if (apiMode === "mock") return <>{children}</>;
  return (
    <>
      <section
        className="card-surface mx-auto my-6 max-w-5xl space-y-3 p-4"
        aria-label="Reviewer session"
      >
        {session.access ? (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm">
              Session supplied. The server checks reviewer access on every request.
            </p>
            <button
              type="button"
              className="rounded-md border px-4 py-2"
              onClick={session.disconnect}
            >
              Sign out
            </button>
          </div>
        ) : (
          <form
            className="space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              const problem = session.connect(token);
              setToken("");
              setError(problem);
            }}
          >
            <h1 className="text-xl font-semibold">Reviewer access</h1>
            <p className="text-sm">
              Enter the reviewer session token supplied privately by your administrator. It stays in
              this tab's memory and is cleared on reload or sign out.
            </p>
            <label className="block text-sm font-semibold">
              Reviewer session token
              <input
                type="password"
                autoComplete="off"
                spellCheck={false}
                value={token}
                onChange={(event) => setToken(event.target.value)}
                className="mt-1 w-full rounded-md border bg-card p-2"
              />
            </label>
            <button type="submit" className="rounded-md border px-4 py-2">
              Connect reviewer session
            </button>
          </form>
        )}
        {error && (
          <p role="alert" className="text-sm">
            {error}
          </p>
        )}
        {session.message && (
          <p role="status" className="text-sm">
            {session.message}
          </p>
        )}
      </section>
      {session.access && <div key={session.revision}>{children}</div>}
    </>
  );
}
