export type JobStatus = "queued" | "generating_final" | "completed" | "failed";

export type AssetKind = "final";

export type GeneratedAsset = {
  id: string;
  kind: AssetKind;
  situationId: string;
  situationLabel: string;
  typeId: "A" | "B" | "C";
  filename: string;
  path: string;
};

export type GenerationJob = {
  id: string;
  status: JobStatus;
  styleId: string;
  styleLabel: string;
  letteringStyleId: string;
  letteringStyleLabel: string;
  letteringStylePrompt: string;
  uploadPath: string;
  uploadMimeType: string;
  characterProfile?: string;
  finalAssets: GeneratedAsset[];
  error?: string;
  createdAt: string;
  updatedAt: string;
};
