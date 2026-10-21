import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./core/styles/fonts.css";
import "./core/styles/tokens.css";
import { App } from "./App";

const root = document.getElementById("root");
if (!root) {
  throw new Error("No existe el elemento #root en index.html");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
