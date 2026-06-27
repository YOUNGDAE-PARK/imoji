export type ModeId = "general" | "tennis";

export type JobStatus = "queued" | "generating_final" | "completed" | "failed";

export type AssetKind = "final";

export type TextOverlayMode = "default" | "custom";

export type TextOverlayItem = {
  id: string;
  text: string;
  x: number;
  y: number;
  rotation: number;
  fontSize: number;
  color: string;
};

export type SituationTextOverlay = {
  mode: TextOverlayMode;
  items: TextOverlayItem[];
};

export type TextOverlayMap = Record<string, SituationTextOverlay>;

export type GeneratedAsset = {
  id: string;
  kind: AssetKind;
  situationId: string;
  situationLabel: string;
  displayText: string;
  typeId: "A" | "B" | "C";
  filename: string;
  path: string;
  mp4Filename?: string;
  mp4Path?: string;
  thumbFilename?: string;
  thumbPath?: string;
  fileSizeKb?: number;
};

export type GenerationJob = {
  id: string;
  status: JobStatus;
  styleId: string;
  styleLabel: string;
  letteringStyleId: string;
  letteringStyleLabel: string;
  letteringStylePrompt: string;
  modeId: ModeId;
  modeLabel: string;
  selectedSituationIds: string[];
  textOverlays?: TextOverlayMap;
  uploadPath: string;
  uploadMimeType: string;
  characterProfile?: string;
  finalAssets: GeneratedAsset[];
  error?: string;
  createdAt: string;
  updatedAt: string;
};
