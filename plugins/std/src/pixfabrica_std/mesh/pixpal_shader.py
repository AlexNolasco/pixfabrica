from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import moderngl
import numpy as np
from PIL import Image

from pixfabrica_std.mesh.shader_helper import set_uniform, write_mvp, write_normal_matrix

PIXPAL_VERT = """
#version 330 core
in vec3 in_pos;
in vec3 in_normal;
in vec2 in_uv;
uniform mat4 u_mvp;
uniform mat4 u_model_view;
uniform mat3 u_normal_matrix;
out vec3 v_normal;
out vec2 v_uv;
out vec3 v_view_pos;
void main() {
    vec4 mv_pos = u_model_view * vec4(in_pos, 1.0);
    v_view_pos = mv_pos.xyz;
    v_normal = u_normal_matrix * in_normal;
    v_uv = in_uv;
    gl_Position = u_mvp * vec4(in_pos, 1.0);
}
"""

PIXPAL_MORPH_VERT = """
#version 330 core
in vec3 in_pos;
in vec3 in_normal;
in vec2 in_uv;
in vec3 in_morph_pos;
in vec3 in_morph_norm;
uniform mat4 u_mvp;
uniform mat4 u_model_view;
uniform mat3 u_normal_matrix;
uniform float u_morph_weight;
out vec3 v_normal;
out vec2 v_uv;
out vec3 v_view_pos;
void main() {
    vec3 pos = in_pos + u_morph_weight * in_morph_pos;
    vec3 norm = in_normal + u_morph_weight * in_morph_norm;
    vec4 mv_pos = u_model_view * vec4(pos, 1.0);
    v_view_pos = mv_pos.xyz;
    v_normal = u_normal_matrix * norm;
    v_uv = in_uv;
    gl_Position = u_mvp * vec4(pos, 1.0);
}
"""

PIXPAL_FRAG = """
#version 330 core
in vec3 v_normal;
in vec2 v_uv;
in vec3 v_view_pos;
uniform sampler2D u_base_color;
uniform sampler2D u_attributes;
uniform sampler2D u_emission;
uniform float u_anim;
uniform float u_roughness_base;
uniform float u_emissive_factor;
uniform float u_ambient;
uniform vec3 u_light_dir;
uniform float u_opacity;
out vec4 frag_color;

void main() {
    vec4 attr = texture(u_attributes, v_uv);
    vec2 palette_uv = vec2(v_uv.x, v_uv.y - attr.b * u_anim);

    vec3 albedo = texture(u_base_color, palette_uv).rgb;
    vec3 emit = texture(u_emission, palette_uv).rgb * u_emissive_factor;

    float metallic = attr.r;
    float roughness = max(u_roughness_base - attr.g, 0.04);

    vec3 n = normalize(v_normal);
    vec3 l = normalize(u_light_dir);
    vec3 v = normalize(-v_view_pos);
    float NdotL = max(dot(n, l), 0.0);

    vec3 diffuse = albedo * (1.0 - metallic) * NdotL;
    vec3 h = normalize(l + v);
    float spec_power = mix(4.0, 128.0, 1.0 - roughness);
    float spec = pow(max(dot(n, h), 0.0), spec_power) * metallic;

    vec3 lit = albedo * u_ambient + diffuse + vec3(spec);

    vec3 color = lit + emit;
    // Premultiplied alpha — GL compositor uses ONE / ONE_MINUS_SRC_ALPHA.
    frag_color = vec4(color * u_opacity, u_opacity);
}
"""

_PALETTE_FILES = {
    "base": "ImphenziaPixPal_BaseColor.png",
    "attributes": "ImphenziaPixPal_Attributes.png",
    "emission": "ImphenziaPixPal_Emission.png",
}


def palette_dir() -> Path:
    return Path(str(files("pixfabrica_std") / "palette"))


def load_pixpal_texture(gl: moderngl.Context, path: Path) -> moderngl.Texture:
    image = Image.open(path).convert("RGBA")
    data = np.array(image, dtype=np.uint8)
    tex = gl.texture(image.size, 4, data.tobytes())
    tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
    tex.repeat_x = True
    tex.repeat_y = True
    return tex


def load_pixpal_textures(gl: moderngl.Context) -> dict[str, moderngl.Texture]:
    root = palette_dir()
    return {
        name: load_pixpal_texture(gl, root / filename) for name, filename in _PALETTE_FILES.items()
    }


def bind_pixpal_textures(prog: moderngl.Program, textures: dict[str, moderngl.Texture]) -> None:
    textures["base"].use(0)
    textures["attributes"].use(1)
    textures["emission"].use(2)
    set_uniform(prog, "u_base_color", 0)
    set_uniform(prog, "u_attributes", 1)
    set_uniform(prog, "u_emission", 2)


def upload_pixpal_mesh(
    gl: moderngl.Context,
    program: moderngl.Program,
    interleaved: np.ndarray,
    indices: np.ndarray,
) -> moderngl.VertexArray:
    vbo = gl.buffer(interleaved.tobytes())
    ibo = gl.buffer(indices.astype(np.uint32).tobytes())
    return gl.vertex_array(
        program,
        [(vbo, "3f 3f 2f", "in_pos", "in_normal", "in_uv")],
        index_buffer=ibo,
    )


def upload_pixpal_morph_mesh(
    gl: moderngl.Context,
    program: moderngl.Program,
    interleaved: np.ndarray,
    indices: np.ndarray,
) -> moderngl.VertexArray:
    vbo = gl.buffer(interleaved.tobytes())
    ibo = gl.buffer(indices.astype(np.uint32).tobytes())
    return gl.vertex_array(
        program,
        [
            (
                vbo,
                "3f 3f 2f 3f 3f",
                "in_pos",
                "in_normal",
                "in_uv",
                "in_morph_pos",
                "in_morph_norm",
            )
        ],
        index_buffer=ibo,
    )


def write_pixpal_uniforms(
    prog: moderngl.Program,
    *,
    mvp: np.ndarray,
    model_view: np.ndarray,
    anim: float,
    roughness_base: float,
    emissive_factor: float,
    ambient: float,
    opacity: float,
    light_dir: tuple[float, float, float],
    morph_weight: float = 0.0,
) -> None:
    write_mvp(prog, mvp)
    set_uniform(prog, "u_model_view", model_view.T.astype("f4").tobytes())
    write_normal_matrix(prog, model_view)
    set_uniform(prog, "u_anim", float(anim))
    set_uniform(prog, "u_roughness_base", float(roughness_base))
    set_uniform(prog, "u_emissive_factor", float(emissive_factor))
    set_uniform(prog, "u_ambient", float(ambient))
    set_uniform(prog, "u_light_dir", light_dir)
    set_uniform(prog, "u_opacity", float(opacity))
    set_uniform(prog, "u_morph_weight", float(morph_weight))
