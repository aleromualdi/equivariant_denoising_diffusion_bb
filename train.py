import os

import torch
from exazyme.tk.Denoising_Diffusion_Repo.model import ProteinDiffusionModel
from torch import nn, optim
from tqdm import tqdm


class Config():
  def __init__(self):
    self.max_seq_length = 256
    self.pos_embed_size = 256
    self.hidden_size = 128
    self.edge_embed_dim = 128
    self.num_egnn_layers = 4
    self.batch_size = 8


cfg = Config()


def save_checkpoint(epoch, model, optimizer, train_losses, checkpoint_path="checkpoint.pth"):
    """Save training checkpoint to a file.

    Args:
        epoch (int): Current epoch number.
        model (nn.Module): The model being trained.
        optimizer (torch.optim.Optimizer): Optimizer used during training.
        train_losses (list): List of training losses recorded during training.
        checkpoint_path (str): File path to save the checkpoint.
    
    """    
    checkpoint = {
        'epoch': epoch,
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'train_losses': train_losses,
    }
    torch.save(checkpoint, checkpoint_path)
    print(f"Checkpoint saved at {checkpoint_path}")


def load_checkpoint(checkpoint_path, model, optimizer=None, new_lr=None):
    """Load training checkpoint from a file.

    Args:
        checkpoint_path (str): File path to the checkpoint.
        model (nn.Module): The model to load the checkpoint into.
        optimizer (torch.optim.Optimizer, optional): Optimizer to load the state into. 
            Defaults to None.
        new_lr (float, optional): If provided, updates the learning rate for the optimizer. 
            Defaults to None.

    Returns:
        int: Starting epoch to resume training.
        list: List of training losses loaded from the checkpoint.
    """
    checkpoint = torch.load(checkpoint_path)
    model.load_state_dict(checkpoint['model_state_dict'])

    if optimizer:
        optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        if new_lr is not None:
            for param_group in optimizer.param_groups:
                param_group['lr'] = new_lr
            print(f"Learning rate updated to {new_lr:.6f}")

    epoch = checkpoint['epoch']
    train_losses = checkpoint['train_losses']
    print(f"Checkpoint loaded: Resuming from epoch {epoch + 1}")
    return epoch, train_losses


# Hyperparameters
device = 'cuda'
num_epochs = 300
learning_rate = 1e-5
diffusion_steps = 1000
beta_start = 0.0001
beta_end = 0.02

checkpoint_path = "checkpoint.pth"

# If resume_training is True and a checkpoint exists, load the model, optimizer,
# and training state from the checkpoint. Optionally update the learning rate.
resume_training = False


model = ProteinDiffusionModel(
    max_residues=cfg.max_seq_length,
    diffusion_steps=diffusion_steps,
    pos_embed_size=cfg.pos_embed_size,
    hidden_size=cfg.hidden_size,
    edge_embed_dim=cfg.edge_embed_dim,
    num_egnn_layers=cfg.num_egnn_layers,
    device=device,
    beta_start=beta_start,
    beta_end=beta_end,
).to(device)

optimizer = optim.Adam(model.parameters(), lr=learning_rate)
loss_fn = nn.MSELoss(reduction='none')


class Config():
  def __init__(self):
    self.max_seq_length = 256
    self.pos_embed_size = 256
    self.hidden_size = 256
    self.edge_embed_dim = 256
    self.num_egnn_layers = 4
    self.batch_size = 4 # 64


cfg = Config()

# Placeholder for a data loader that yields batches containing keys: 'residue_index', 
# 'atom_mask', and 'atom_positions'
train_loader = None 

# Training loop
train_losses = []

# Load from checkpoint if resuming
start_epoch = 0
if resume_training and os.path.exists(checkpoint_path):
    start_epoch, train_losses = load_checkpoint(checkpoint_path, model, optimizer, new_lr=1e-7)

for epoch in range(start_epoch, num_epochs):
    model.train()
    epoch_loss = 0
    total_samples = 0  # Track the total number of valid atoms for normalization
    progress_bar = tqdm(train_loader, desc=f"Epoch {epoch + 1}/{num_epochs}")

    for batch in progress_bar:
        residue_indices = batch['residue_index'].to(device)  # Shape: [B, N]
        atom_mask = batch['atom_mask'].to(device)  # Shape: [B, N, num_atoms]
        coords = batch['atom_positions'].to(device)  # Shape: [B, N, num_atoms, 3]

        # Sample random time steps for the batch
        t = torch.randint(0, diffusion_steps, (coords.size(0),), device=device)  # Shape: [B]

        # Add noise using the forward diffusion process
        noise = torch.randn_like(coords)  # [B, N, num_atoms, 3]
        alpha_cumprod = model.alpha_cumprod[t].view(-1, 1, 1, 1)  # Shape: [B, 1, 1, 1]
        noisy_coords = torch.sqrt(alpha_cumprod) * coords + torch.sqrt(1 - alpha_cumprod) * noise  # [B, N, num_atoms, 3]

        # Forward pass: predict noise and reconstructed coordinates
        predicted_noise = model(noisy_coords, residue_indices, t, atom_mask)  # [B, N, num_atoms, 3]

        # Compute noise prediction loss
        loss = loss_fn(predicted_noise, noise)  # [B, N, num_atoms, 3]
        loss = (loss * atom_mask.unsqueeze(-1)).sum()

        epoch_loss += loss.item()
        total_samples += atom_mask.sum().item()  # Accumulate total valid atoms

        # Backpropagation
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

    # Normalize training loss by the total number of valid atoms
    avg_train_loss = epoch_loss / total_samples

    print(f"Epoch {epoch + 1}/{num_epochs}, Train Loss: {avg_train_loss:.4f}")

    train_losses.append(avg_train_loss)

    # Save the model every 10 epochs
    if (epoch + 1) % 10 == 0:
        save_checkpoint(epoch, model, optimizer, train_losses, checkpoint_path)
