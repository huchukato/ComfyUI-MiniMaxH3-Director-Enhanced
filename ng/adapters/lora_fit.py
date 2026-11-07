"""Put a LoRA on a model, leaving out the pieces whose shape does not fit it.

The non-pruned turbo LoRA (`minimax_h3_turbo_4step_ckpt500`) carries AdaLN pieces for the full model (input 2688); the pruned
H3 models have an AdaLN input of 8. ComfyUI then logged "ERROR lora ...adaln_proj.linear.weight shape '[96768, 8]' is invalid
for input of size 260112384" 51 times per step and skipped them (user log, 2026-10-11). Left out here, with one note instead.
"""
import math


def _target(key):
    return key[0] if isinstance(key, tuple) else key


def _weight(model, name):
    value = model
    for part in name.split("."):
        value = getattr(value, part, None)
        if value is None:
            return None
    return value


def _product_size(patch):
    """Elements of the weight change a plain LoRA piece makes (up @ down), or None when it is another kind of patch."""
    if type(patch).__name__ != "LoRAAdapter":
        return None
    up, down, _alpha, mid = patch.weights[:4]
    if mid is not None:
        return None
    return int(up.shape[0]) * int(math.prod(down.shape[1:]))


def fitting(model, loaded):
    """(patches that fit `model`, names left out). `model` is the torch module the keys point into."""
    keep, left_out = {}, []
    for key, patch in loaded.items():
        weight, size = _weight(model, _target(key)), _product_size(patch)
        if weight is not None and size is not None and size != int(math.prod(weight.shape)):
            left_out.append(_target(key))
            continue
        keep[key] = patch
    return keep, left_out


def apply(model_patcher, lora, strength):
    """The LoRA state dict on a clone of the model patcher, as comfy.sd.load_lora_for_models does. Returns (patcher, left out)."""
    import comfy.lora
    import comfy.lora_convert
    key_map = comfy.lora.model_lora_keys_unet(model_patcher.model, {})
    loaded = comfy.lora.load_lora(comfy.lora_convert.convert_lora(lora), key_map)
    keep, left_out = fitting(model_patcher.model, loaded)
    patched = model_patcher.clone()
    patched.add_patches(keep, strength)
    return patched, left_out
