"""AI configuration is shared by connected contexts; loading it makes no requests."""
from comfy_api.latest import io
import folder_paths

from ..adapters.ai_provider import provider_from_values
from ..core import providers
from .context_nodes import CATEGORY

NGAI = io.Custom("NG_AI_PROVIDER")


class NGAIProvider(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="NGAIProvider", display_name="H3 AI Loader", category=CATEGORY,
                         description="Connect a generative CLIP loader, local model server or compatible API. The AI only runs when you press an AI button (Analyze, Make H3 prompt, AI: split into shots, Write with AI).",
                         inputs=[io.String.Input("source", default="local", tooltip="Which kind of provider the fields below belong to. The panel on the node shows the matching address and options."),
                                 io.Combo.Input("provider", options=sorted(providers.PROVIDERS), default="ollama",
                                                tooltip="Which server or API to talk to. Each one has its own address and its own set of settings."),
                                 io.String.Input("base_url", default="", tooltip="Address of the selected provider. The panel offers its standard address."),
                                 io.String.Input("model", default="", tooltip="Model served by your selected provider."),
                                 io.String.Input("api_key_env", default="", advanced=True, tooltip="Environment variable containing the key; never paste the key here."),
                                 io.Boolean.Input("vision", default=True, tooltip="Declare that the selected model accepts images."),
                                 io.Boolean.Input("audio", default=False, tooltip="Declare input_audio support; not supported by this Ollama transport."),
                                 io.Int.Input("timeout_seconds", default=120, min=5, max=900, advanced=True,
                                              tooltip="How long one analysis request may take before it is given up."),
                                 io.Int.Input("max_tokens", default=512, min=64, max=8192, advanced=True,
                                              tooltip="Upper bound for the answer length. A short description needs few tokens."),
                                 io.Int.Input("keep_alive", default=0, min=0, max=3600, advanced=True,
                                              tooltip="Seconds the provider keeps the model loaded. 0 releases it after every request."),
                                 io.Float.Input("temperature", default=0.3, min=0.0, max=2.0, step=0.05, advanced=True,
                                                tooltip=providers.SETTING_HELP["temperature"]),
                                 io.Float.Input("top_p", default=0.9, min=0.0, max=1.0, step=0.05, advanced=True,
                                                tooltip=providers.SETTING_HELP["top_p"]),
                                 io.Int.Input("top_k", default=40, min=0, max=100, advanced=True,
                                              tooltip=providers.SETTING_HELP["top_k"]),
                                 io.Float.Input("min_p", default=0.0, min=0.0, max=1.0, step=0.01, advanced=True,
                                                tooltip=providers.SETTING_HELP["min_p"]),
                                 io.Float.Input("frequency_penalty", default=0.0, min=-2.0, max=2.0, step=0.1, advanced=True,
                                                tooltip=providers.SETTING_HELP["frequency_penalty"]),
                                 io.Float.Input("presence_penalty", default=0.0, min=-2.0, max=2.0, step=0.1, advanced=True,
                                                tooltip=providers.SETTING_HELP["presence_penalty"]),
                                 # control_after_generate=False is the whole point of this line, and it
                                 # is not the default. ComfyUI's frontend hangs a "control after
                                 # generate" switch on ANY widget named "seed" unless this is set - the
                                 # check reads `control_after_generate ?? name in ["seed","noise_seed"]`,
                                 # so only an explicit False suppresses it. The panel has its own
                                 # "Fixed seed" switch right beside this field, and that one is the
                                 # honest control: the provider picks the seed, not the queue. Two
                                 # controls for one decision is how the user ticks randomize and then
                                 # wonders why fixed_seed says otherwise.
                                 io.Int.Input("seed", default=0, min=0, max=2 ** 32 - 1,
                                              control_after_generate=False,
                                              tooltip=providers.SETTING_HELP["seed"]),
                                 io.Boolean.Input("fixed_seed", default=False,
                                                  tooltip=providers.SETTING_HELP["fixed_seed"]),
                                 io.Clip.Input("clip", display_name="CLIP", raw_link=True, lazy=True, optional=True,
                                               tooltip="For CLIP / Encoder: connect a generative text/vision model. H3's conditioning CLIP stays independently connected at the Connector."),
                                 io.Combo.Input("local_model", options=[""] + folder_paths.get_filename_list("text_encoders"), default="", advanced=True, optional=True,
                                               tooltip="Use an installed text encoder instead of a connected Load CLIP node. Loaded only during an explicit AI action."),
                                 io.Combo.Input("local_type", options=["stable_diffusion", "ltxv", "minimax"], default="stable_diffusion", advanced=True, optional=True,
                                                tooltip="Which loader ComfyUI needs for your chosen encoder file.")],
                         outputs=[NGAI.Output(display_name="AI provider")])

    @classmethod
    def execute(cls, **values):
        source = values.pop("source", "local")
        clip = values.pop("clip", None)
        return io.NodeOutput(provider_from_values(source, clip, values))


NODES = [NGAIProvider]
