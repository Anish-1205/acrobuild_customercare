import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { RoleProvider } from "./contexts/RoleContext";
import { SearchProvider } from "./contexts/SearchContext";
import App from "./App";
import "./styles.css";
import "./customer-home-refresh.css";
import "./customer-home-v2.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RoleProvider>
      <SearchProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </SearchProvider>
    </RoleProvider>
  </React.StrictMode>
);

