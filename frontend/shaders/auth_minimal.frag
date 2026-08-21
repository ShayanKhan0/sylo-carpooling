#include <flutter/runtime_effect.glsl>

uniform vec2 uSize;
uniform float uTime;
uniform float uIntensity;

out vec4 fragColor;

float softStripe(vec2 uv, float phase) {
  float wave = sin((uv.x * 9.0) + (uv.y * 6.5) + phase);
  return smoothstep(0.52, 0.95, 0.5 + (0.5 * wave));
}

void main() {
  vec2 fragCoord = FlutterFragCoord().xy;
  vec2 uv = fragCoord / uSize;
  float pulse = (sin(uTime * 0.7) * 0.5) + 0.5;

  float stripeA = softStripe(uv, uTime * 0.65);
  float stripeB = softStripe(vec2(1.0 - uv.y, uv.x), -uTime * 0.48);
  float stripe = mix(stripeA, stripeB, 0.42);

  float vignette = smoothstep(1.08, 0.2, distance(uv, vec2(0.5, 0.5)));
  float alpha = stripe * vignette * ((0.72 * uIntensity) + (0.02 * pulse));

  // Neutral black overlay preserves the original page gradient colors.
  fragColor = vec4(0.0, 0.0, 0.0, alpha);
}
