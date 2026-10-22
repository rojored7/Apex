import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./core/styles/fonts.css";
import "./core/styles/tokens.css";
import { App } from "./App";
import { installSessionBridge } from "./core/auth/session";

const root = document.getElementById("root");
if (!root) {
  throw new Error("No existe el elemento #root en index.html");
}

// S2-F3: el token y el refresh compartido (gancho del 401, canal apex-auth) quedan conectados
// con el cliente del api antes de la primera petición.
installSessionBridge();

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
