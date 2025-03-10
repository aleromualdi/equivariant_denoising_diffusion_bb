import torch
from tqdm import tqdm


def sample_protein_backbone(
    model, diffusion_steps, max_residues, device='cuda', init_scale=1.0, noise_scale=1.0
):
    """Generate a protein backbone using the diffusion model with integrated reconstruction.

    Args:
        model: Trained ProteinDiffusionModel.
        diffusion_steps: Total diffusion steps (T).
        max_residues: Maximum residues in the sequence.
        device: Device to run the sampling on ('cuda' or 'cpu').
        init_scale: Initial noise scale for coordinates.
        noise_scale: Noise scale during reverse diffusion steps.

    Returns:
        Generated full atomic coordinates (with non-backbone atoms set to zero) as a NumPy array.
    
    """
    model.eval()

    num_atoms = model.num_atoms  # to ensure cnsistency with model params
    backbone_indices = [0, 1, 2, 4]  # Indices for (N, CA, C, O)

    # Initialize random noisy coordinates
    coords = torch.randn(1, max_residues, num_atoms, 3, device=device) * init_scale
    residue_indices = torch.arange(max_residues, device=device).unsqueeze(0)

    # atom mask for (N, CA, C, O)
    atom_mask = torch.zeros(1, max_residues, num_atoms, device=device)
    atom_mask[:, :, backbone_indices] = 1

    # Sampling loop
    alpha_cumprod_prev = model.alpha_cumprod_prev

    with torch.no_grad():
        for t in tqdm(range(diffusion_steps - 1, -1, -1), desc="Sampling"):
            t_tensor = torch.tensor([t], device=device).long()

            # Predict noise added to the coordinates
            predicted_noise = model(coords, residue_indices, t_tensor, atom_mask)

            # Compute mean for x_{t-1}
            alpha_t_prev = alpha_cumprod_prev[t].view(1, 1, 1, 1)
            alpha_t = model.alpha_cumprod[t].view(1, 1, 1, 1)

            mean_coords = (
                torch.sqrt(alpha_t_prev) * coords -
                torch.sqrt(1 - alpha_t_prev) * predicted_noise
            ) / torch.sqrt(alpha_t)

            # Add noise for t > 0
            if t > 0:
                z = torch.randn_like(coords) * noise_scale
            else:
                z = torch.zeros_like(coords)  # No noise at final step

            coords = mean_coords + z

            # Apply atom mask to preserve backbone structure
            coords = coords * atom_mask.unsqueeze(-1) + (1 - atom_mask.unsqueeze(-1)) * coords

            # Clip coordinates to a reasonable range
            coords = torch.clamp(coords, min=-10.0, max=10.0)

            # Logging every 100 steps or at the final step
            if t % 100 == 0 or t == 0:
                print(f"Step {t}: Coords mean={coords.mean().item():.4f}, std={coords.std().item():.4f}")

    # non-backbone atom coordinates to zero
    coords = coords * atom_mask.unsqueeze(-1)
    coords = coords.squeeze(0) # Remove batch dimension

    return coords.cpu().detach().numpy()


model = None # trained model

# diffusion_steps and max_residues should match training settings
diffusion_steps = 1000
max_residues = 256

with torch.no_grad():
    generated_backbone = sample_protein_backbone(model, diffusion_steps, max_residues)

print(f"Generated backbone shape: {generated_backbone.shape}")