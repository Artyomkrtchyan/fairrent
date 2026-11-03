import { createContext, useContext, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { apiBaseUrl, apiMode } from "@/api/client";
import type { ReviewerAccess } from "@/api/reviews";

interface Session {
  access: ReviewerAccess | undefined;
  revision: number;
  message: string;
  connect: (token: string) => string | null;
  disconnect: () => void;
}

const Context = createContext<Session | null>(null);

export function ReviewerSessionProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const active = useRef<ReviewerAccess | undefined>(undefined);
  const [access, setAccess] = useState<ReviewerAccess>();
  const [revision, setRevision] = useState(0);
  const [message, setMessage] = useState("");

  function clear(nextMessage: string) {
    active.current?.controller.abort();
    active.current = undefined;
    client.removeQueries({ predicate: (query) => String(query.queryKey[0]).startsWith("review-") });
    for (const mutation of client
      .getMutationCache()
      .findAll({ mutationKey: ["review-decision"] })) {
      client.getMutationCache().remove(mutation);
    }
    setAccess(undefined);
    setRevision((value) => value + 1);
    setMessage(nextMessage);
  }

  function connect(value: string) {
    if (apiMode !== "real") return "Synthetic preview does not accept reviewer sessions.";
    const token = value.trim();
    if (!/^[A-Za-z0-9_-]{43}$/.test(token))
      return "Enter the session token supplied by your administrator.";
    const urls = [new URL(window.location.href), new URL(apiBaseUrl, window.location.origin)];
    if (
      urls.some(
        (url) =>
          url.protocol !== "https:" &&
          !(url.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)),
      )
    ) {
      return "Reviewer sessions require HTTPS outside local development.";
    }
    clear("");
    const next: ReviewerAccess = {
      token,
      controller: new AbortController(),
      reject: (reason) => {
        if (active.current === next) clear(reason);
      },
    };
    active.current = next;
    setAccess(next);
    return null;
  }

  return (
    <Context.Provider
      value={{
        access,
        revision,
        message,
        connect,
        disconnect: () => clear("Session cleared from this tab."),
      }}
    >
      {children}
    </Context.Provider>
  );
}

export function useReviewerSession() {
  const session = useContext(Context);
  if (!session) throw new Error("ReviewerSessionProvider is required.");
  return session;
}
