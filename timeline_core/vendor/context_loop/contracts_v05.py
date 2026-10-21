"""Only the two upstream recipe constants required by these vendored modules."""

DRIFT_CONTROL_AV_RECIPE = {
    "version": "h3_drift_control_av_v1",
    "context_frames": 39,
    "video_steps": 12,
    "matched_steps": 8,
    "taper_steps": 4,
    "sigma_rule": "next_schedule_sigma_over_current_sigma",
    "mask_quantization": 256,
    "audio": "unchanged_policy_mask",
    "validated_steps": 20,
}

LATENT_COLOR_CARRY_RECIPE = {
    "version": "h3_latent_color_delta_v1",
    "context_frames": 39,
    "video_steps": 12,
    "anchor": "first_generated_scene_delivered_tail",
    "source": "current_predecessor_delivered_tail",
    "strength": 0.50,
    "max_luma_shift_code_values": 6.0,
    "max_saturation_change": 0.06,
    "spatial_lowpass_kernel": 3,
    "temporal_taper": "full_prefix_smoothstep_zero_to_one",
    "delta_rule": "E(graded_D(z))-E(D(z))",
    "audio": "unchanged",
}
