// S2-F2: raíz de la app. TanStack Query, el rol de la sesión para useCan/<Can> y el router
// creado desde config/routeTable.ts. El router se crea una sola vez por montaje.
import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { RouterProvider } from "react-router";
import { queryClient } from "./core/api/queryClient";
import { SessionRoleProvider } from "./core/auth/SessionRole";
import { createAppRouter, type AppRouter } from "./routes";

export interface AppProps {
  /** Router ya creado (pruebas); por defecto, el del navegador. */
  router?: AppRouter;
}

export function App({ router }: AppProps) {
  const [appRouter] = useState(() => router ?? createAppRouter());
  return (
    <QueryClientProvider client={queryClient}>
      <SessionRoleProvider>
        <RouterProvider router={appRouter} />
      </SessionRoleProvider>
    </QueryClientProvider>
  );
}
