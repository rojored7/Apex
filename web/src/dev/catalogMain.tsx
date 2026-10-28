// Entrada de catalog.html (US-062 T5 y US-068 T5): páginas de muestra de los layouts y del
// kit para las pruebas de Playwright y la revisión visual. Solo entra al build con
// `vite build --mode catalog` (`npm run build:catalog`); el build de producción y la imagen
// de Nginx no la incluyen.
// S3-D105: zodSetup va antes de cualquier esquema (jitless, CSP sin eval); no lo reordenes.
import "../core/zodSetup";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../core/styles/fonts.css";
import "../core/styles/tokens.css";
import { CatalogApp } from "./Catalog";

const root = document.getElementById("root");
if (!root) {
  throw new Error("No existe el elemento #root en catalog.html");
}

createRoot(root).render(
  <StrictMode>
    <CatalogApp />
  </StrictMode>,
);
