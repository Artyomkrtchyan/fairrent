import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
  type ErrorComponentProps,
} from "@tanstack/react-router";

import { PrefsProvider } from "@/lib/prefs";
import { ReviewerSessionProvider } from "@/lib/reviewer-session";
import { SiteFooter, SiteHeader } from "@/components/SiteHeader";

function NotFoundComponent() {
  return (
    <main className="mx-auto max-w-xl px-4 py-24 text-center">
      <p className="font-display text-7xl font-bold text-primary">404</p>

      <h1 className="mt-4 text-2xl font-semibold">This page isn't on the map</h1>

      <p className="mt-2 text-muted-foreground">
        The page or listing you're looking for doesn't exist or has been removed.
      </p>

      <Link
        to="/"
        className="mt-6 inline-flex rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
      >
        Back to rentals
      </Link>
    </main>
  );
}

function ErrorComponent({ reset }: ErrorComponentProps) {
  const router = useRouter();

  return (
    <div className="flex min-h-[60vh] items-center justify-center px-4">
      <div className="max-w-md text-center">
        <h1 className="text-xl font-semibold">This page didn't load</h1>

        <p className="mt-2 text-sm text-muted-foreground">
          Something went wrong. You can try again or head back home.
        </p>

        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <button
            onClick={() => {
              void router.invalidate();
              reset();
            }}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
          >
            Try again
          </button>

          <a href="/" className="rounded-md border px-4 py-2 text-sm font-medium">
            Go home
          </a>
        </div>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootComponent() {
  const { queryClient } = Route.useRouteContext();

  return (
    <QueryClientProvider client={queryClient}>
      <PrefsProvider>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
        >
          Skip to content
        </a>

        <SiteHeader />

        <div id="main" className="min-h-[70vh]">
          <ReviewerSessionProvider>
            <Outlet />
          </ReviewerSessionProvider>
        </div>

        <SiteFooter />
      </PrefsProvider>
    </QueryClientProvider>
  );
}
