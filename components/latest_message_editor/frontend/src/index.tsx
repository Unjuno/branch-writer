import React from "react"
import ReactDOM from "react-dom/client"
import { Streamlit, withStreamlitConnection } from "@streamlit/component-lib"
import LatestMessageEditor from "./LatestMessageEditor"
import "./style.css"

const ConnectedLatestMessageEditor = withStreamlitConnection(LatestMessageEditor)

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ConnectedLatestMessageEditor />
  </React.StrictMode>,
)

Streamlit.setFrameHeight()
