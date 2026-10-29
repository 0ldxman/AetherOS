import { mount } from "svelte";
// шрифты свои: студия выглядит одинаково на любой машине, системные шрифты не нужны
import "@fontsource-variable/inter";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/600.css";
import "./app.css";
import App from "./App.svelte";

mount(App, { target: document.getElementById("app")! });
