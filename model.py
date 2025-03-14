import numpy as np
import torch
from torch import nn


def sinusoidal_positional_encoding(x, embed_dim, embed_size):
    """Creates sine/cosine positional embeddings as described in the paper
    "Attention is All You Need" by Vaswani et al.
    
    This mechanism encodes positional information in a sequence to allow
    models to leverage structural and temporal relationships effectively.

    Args:
        x: Tensor of shape [B, N, N] or [B, N], representing input indices or positions.
        embed_dim: Dimension of the positional embeddings.
        embed_size: A scaling factor that determines the frequency range of the embeddings.

    Returns:
        Tensor with sinusoidal positional encodings.
        - Shape: [B, N, N, embed_dim] for pairwise residue offsets.
        - Shape: [B, embed_dim] for timestep encodings.
    
    """
    pi = np.pi
    inv_freq = 1.0 / (embed_size ** (2 * torch.arange(embed_dim // 2, dtype=torch.float32) / embed_dim))
    inv_freq = inv_freq.to(x.device)

    # Compute sinusoidal encoding
    angles = x[..., None] * pi * inv_freq  # [..., embed_dim/2]
    pos_embedding_sin = torch.sin(angles)  # Sine component
    pos_embedding_cos = torch.cos(angles)  # Cosine component

    pos_embedding = torch.cat([pos_embedding_sin, pos_embedding_cos], dim=-1)  # [..., embed_dim]
    return pos_embedding


class ProteinDiffusionModel(nn.Module):
    """A denoising diffusion probabilistic model (DDPM) for protein backbone structure
    generation.

    This model leverages a series of equivariant graph neural network (EGNN) layers
    to predict noise added during the diffusion process and reconstruct coordinates
    from noisy inputs.
    
    """ 
    def __init__(
        self,
        max_residues: int,
        diffusion_steps: int,
        pos_embed_size: int,
        hidden_size: int,
        edge_embed_dim: int,
        num_egnn_layers: int,
        num_atoms: int = 37,
        beta_start: float = 0.0001,
        beta_end: float = 0.02,
        device: str = "cuda",
    ):
        """Initializes the ProteinDiffusionModel with the specified parameters.

        Args:
            max_residues (int): Maximum number of residues in a protein.
            diffusion_steps (int): Total number of diffusion steps.
            pos_embed_size (int): Size of the positional embedding.
            hidden_size (int): Hidden dimension size for node features.
            edge_embed_dim (int): Dimension of edge embeddings for the EGNN layers.
            num_egnn_layers (int): Number of EGNN layers.
            num_atoms (int): Number of atoms per residue (default: 37).
            beta_start (float): Starting value for the noise schedule.
            beta_end (float): Ending value for the noise schedule.
            device (str): Device to run the model on
        """
        super(ProteinDiffusionModel, self).__init__()
        self.device = device
        self.max_residues = max_residues
        self.num_atoms = num_atoms
        self.diffusion_steps = diffusion_steps
        self.pos_embed_size = pos_embed_size
        self.hidden_size = hidden_size
        self.edge_embed_dim = edge_embed_dim

        # Noise schedule
        self.betas = torch.linspace(beta_start, beta_end, diffusion_steps, device=device)
        self.alphas = 1.0 - self.betas
        self.alpha_cumprod = torch.cumprod(self.alphas, dim=0).to(device)
        self.alpha_cumprod_prev = torch.cat(
            [torch.tensor([1.0], device=device), self.alpha_cumprod[:-1]]
        )   # α_{t-1}
        
        # EGNN Layers
        self.egnn_layers = nn.ModuleList([
            EGNNLayer(
                input_nf=hidden_size,
                hidden_nf=hidden_size,
                output_nf=hidden_size,
                edge_embed_dim=edge_embed_dim,
                max_len=self.max_residues
            )
            for _ in range(num_egnn_layers)
        ])

    def forward(self, coords, residue_indices, times, atom_mask):
        """Forward pass through the ProteinDiffusionModel.

        Args:
            coords (torch.Tensor): Input coordinates with shape [B, N, num_atoms, 3].
            residue_indices (torch.Tensor): Residue indices with shape [B, N].
            times (torch.Tensor): Time steps for diffusion with shape [B].
            atom_mask (torch.Tensor): Mask for valid atoms with shape [B, N, num_atoms].

        Returns:
            Tuple[torch.Tensor, torch.Tensor]:
                - predicted_noise: Predicted noise added during diffusion, 
                    shape [B, N, num_atoms, 3].
                - reconstructed_coords: Reconstructed coordinates from noisy inputs,
                    shape [B, N, num_atoms, 3].
        
        """        
        batch_size, seq_len, num_atoms, coord_dim = coords.shape
         
        # Residue index embedding
        residue_embedding = sinusoidal_positional_encoding(
            residue_indices.float(), embed_dim=self.hidden_size, embed_size=self.max_residues
        )  # [B, N, hidden_size]

        # Time embedding
        times = times.float() / self.diffusion_steps  # Normalize time to [0, 1]
        time_embedding = sinusoidal_positional_encoding(times, self.hidden_size, 10000)  # [B, hidden_size]
        time_embedding = time_embedding.unsqueeze(1).expand(-1, seq_len, -1)  # [B, N, hidden_size]

        # Initial node features
        node_features = residue_embedding + time_embedding  # [B, N, hidden_size]

        # Current coords (being updated)
        curr_coords = coords.clone()
        
        # Pass through EGNN layers
        for layer in self.egnn_layers:
            curr_coords, node_features = layer(curr_coords, node_features, atom_mask, residue_indices)

        # Compute predicted noise (e_t)
        cum_a_t = self.alpha_cumprod[times.long()].unsqueeze(-1).unsqueeze(-1).unsqueeze(-1)  # [B, 1, 1, 1]
        predicted_noise = (coords - torch.sqrt(cum_a_t) * curr_coords) / torch.sqrt(1 - cum_a_t) # DDPM formula

        return predicted_noise * atom_mask.unsqueeze(-1)


class EGNNLayer(nn.Module):
    """Equivariant Graph Neural Network (EGNN) layer with directional vectors for rotation equivariance."""
    def __init__(self, input_nf, hidden_nf, output_nf, edge_embed_dim=128, max_len=256):
        """
        Initializes the EGNNLayer.

        Args:
            input_nf (int): Dimensionality of input node features.
            hidden_nf (int): Dimensionality of hidden features.
            output_nf (int): Dimensionality of output node features.
            edge_embed_dim (int): Dimensionality of edge embeddings (default: 16).
            max_len (int): Maximum number of residues in the protein sequence (default: 256).
        """
        super(EGNNLayer, self).__init__()
        self.edge_embed_dim = edge_embed_dim
        self.max_len = max_len

        # Edge feature MLP
        self.edge_mlp = nn.Sequential(
            nn.Linear(2 * input_nf + edge_embed_dim + 3, hidden_nf),  # +3 for directional vector
            nn.SiLU(),
            nn.Linear(hidden_nf, hidden_nf),
            nn.SiLU(),
        )

        # Node feature MLP
        self.node_mlp = nn.Sequential(
            nn.Linear(input_nf + hidden_nf, hidden_nf),
            nn.SiLU(),
            nn.Linear(hidden_nf, output_nf),
        )
        self.node_norm = nn.LayerNorm(output_nf)

        # Coordinate update MLP
        self.coord_mlp = nn.Sequential(
            nn.Linear(hidden_nf, hidden_nf),
            nn.SiLU(),
            nn.Linear(hidden_nf, 1),
        )

    def forward(self, coords, node_features, atom_mask, residue_indices):
        """
        Forward pass through the EGNNLayer.

        Args:
            coords (torch.Tensor): Input coordinates of shape [B, N, num_atoms, 3].
            node_features (torch.Tensor): Node features of shape [B, N, input_nf].
            atom_mask (torch.Tensor): Binary mask indicating valid atoms, of shape [B, N, num_atoms].
            residue_indices (torch.Tensor): Residue indices, of shape [B, N].

        Returns:
            Tuple[torch.Tensor, torch.Tensor]:
                - updated_coords: Updated coordinates after applying coordinate updates,
                  shape [B, N, num_atoms, 3].
                - updated_node_features: Updated node features after processing, shape [B, N, output_nf].
        """
        batch_size, seq_len, num_atoms, coord_dim = coords.shape

        # Compute relative residue index differences
        rel_residue_indices = residue_indices[:, :, None] - residue_indices[:, None, :]  # [B, N, N]
        rel_residue_enc = sinusoidal_positional_encoding(
            rel_residue_indices, self.edge_embed_dim, self.max_len)  # [B, N, N, edge_embed_dim]

        # Compute directional vectors
        directional_vectors = coords[:, :, None, :, :] - coords[:, None, :, :, :]  # [B, N, N, num_atoms, 3]
        directional_vectors = directional_vectors.mean(dim=3)  # Mean over atoms, shape [B, N, N, 3]

        # Concatenate edge features
        edge_features = torch.cat(
            [
                node_features[:, :, None, :].expand(-1, -1, seq_len, -1),  # Node features i
                node_features[:, None, :, :].expand(-1, seq_len, -1, -1),  # Node features j
                rel_residue_enc,                                           
                directional_vectors,                                       
            ],
            dim=-1,
        )  # [B, N, N, 2 * input_nf + edge_embed_dim + 3]

        # Process edge features through MLP
        edge_messages = self.edge_mlp(edge_features)  # [B, N, N, hidden_nf]

        # Aggregate messages for nodes
        aggregated_messages = edge_messages.sum(dim=2)  # [B, N, hidden_nf]
        updated_node_features = self.node_mlp(
            torch.cat([node_features, aggregated_messages], dim=-1)
        )  # [B, N, output_nf]
        updated_node_features = self.node_norm(updated_node_features)

        # Coordinate updates using directional vectors
        coord_updates = self.coord_mlp(edge_messages)  # [B, N, N, 1]
        coord_updates = coord_updates * directional_vectors 
        coord_updates = coord_updates.sum(dim=2)  # Aggregate over neighbors, [B, N, 3]

        # Update coordinates
        updated_coords = coords + coord_updates.unsqueeze(2) * atom_mask.unsqueeze(-1)  # [B, N, num_atoms, 3]

        return updated_coords, updated_node_features

