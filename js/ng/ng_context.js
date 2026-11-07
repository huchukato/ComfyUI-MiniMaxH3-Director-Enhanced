// The frontend gives an audio-upload widget its player only for a fixed list of core node names, and the upload widget
// looks the player up by name while it is being built, so the player has to exist BEFORE it. Without this the audio
// context node cannot even be constructed.
const { app } = window.comfyAPI.app;

function withPlayerBeforeUpload(required) {
  const ordered = {};
  for (const [name, definition] of Object.entries(required)) {
    if (name === "upload") ordered.audioUI = ["AUDIO_UI", {}];
    ordered[name] = definition;
  }
  if (!ordered.audioUI) ordered.audioUI = ["AUDIO_UI", {}];
  return ordered;
}

app.registerExtension({
  name: "mmxd.ng.context_audio",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeType.prototype.comfyClass === "NGContextAudio") {
      nodeData.input.required = withPlayerBeforeUpload(nodeData.input.required);
    }
  },
});

// One accent per medium for the cards (h3c_card.js): pictures blue, clips orange, sounds violet, notes teal.
export const FAMILY = {
  NGContextImage: { color: "#28baff", bgcolor: "#101a2c" },
  NGContextVideo: { color: "#e8b274", bgcolor: "#101a2c" },
  NGContextAudio: { color: "#aa7cff", bgcolor: "#101a2c" },
  NGContextText: { color: "#7acdbb", bgcolor: "#101a2c" },
};
