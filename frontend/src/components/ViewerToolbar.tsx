import type { ViewerTool } from "../lib/cornerstone";

const TOOLS: { id: ViewerTool; label: string; hint: string }[] = [
  { id: "WindowLevel", label: "Window / level", hint: "Drag to change brightness and contrast" },
  { id: "Pan", label: "Pan", hint: "Drag to move the image" },
  { id: "Zoom", label: "Zoom", hint: "Drag up or down to zoom" },
  { id: "Length", label: "Measure", hint: "Click two points to measure a length" },
];

interface Props {
  activeTool: ViewerTool;
  onToolChange: (tool: ViewerTool) => void;
  onReset: () => void;
  extras?: React.ReactNode;
}

export function ViewerToolbar({ activeTool, onToolChange, onReset, extras }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-1 rounded-lg border border-slate-200 bg-white p-1">
      {TOOLS.map((tool) => (
        <button
          key={tool.id}
          type="button"
          title={tool.hint}
          onClick={() => onToolChange(tool.id)}
          className={`focus-ring rounded-md px-3 py-1.5 text-xs font-medium transition ${
            activeTool === tool.id
              ? "bg-clinical-600 text-white"
              : "text-slate-600 hover:bg-slate-100"
          }`}
        >
          {tool.label}
        </button>
      ))}
      <span className="mx-1 h-5 w-px bg-slate-200" />
      <button
        type="button"
        onClick={onReset}
        title="Fit the image and reset zoom and pan"
        className="focus-ring rounded-md px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100"
      >
        Reset view
      </button>
      {extras}
    </div>
  );
}
