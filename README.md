# Denoising Diffusion with Equivariance for Protein Backbone Generation

This repository implements a **denoising diffusion probabilistic model (DDPM)** tailored to generate realistic protein backbone structures. The approach integrates **Equivariant Graph Neural Networks (EGNNs)**, ensuring robust handling of geometric transformations like rotation and translation. The repository is designed for ease of understanding, experimentation, and extension.

---

## **Data Representation**

Protein backbone structures are represented as:

- **Point clouds of atomic coordinates**: (`N`, `Cα`, `C`, `O`).
- **Positional and mask arrays**: Identify known and missing atoms.
- **Residue indices**: Encode the sequence position of amino acids.

The **CATH dataset** ([CATH: Protein Structure Classification](https://www.cathdb.info/)) is commonly used as a source of protein backbone data.

---

## **Model Architecture**

The model leverages **Equivariant Graph Neural Networks (EGNNs)** to ensure geometric consistency. Core components include:

### **1. Sinusoidal Positional Encoding**  
Encodes residue indices and diffusion time steps for smooth learning.

### **2. EGNN Layers**  
Update node and edge features while maintaining equivariance.

### **3. Directional Vectors for Equivariance**  

The model explicitly computes and uses **directional vectors**:

$$
\mathbf{v}_{ij} = \mathbf{x}_j - \mathbf{x}_i
$$

Where:
- $\mathbf{x}_i$  and $\mathbf{x}_j$ are the coordinates of residues $i$ and $j$ respectively.

These directional vectors inherently transform correctly under geometric transformations:

- **Rotational Transformation**: When the entire protein structure is rotated, these directional vectors rotate accordingly, preserving their relative orientation.
- **Translation Independence**: Translating the entire structure does not alter these vectors, as they are calculated relative to pairs of residues.

This design ensures that the message-passing and coordinate-update mechanisms in the EGNN layers remain equivariant. All calculations are based on relative features rather than absolute positions, ensuring robust predictions for the spatially complex nature of protein backbones.

---

## **Code Organization**

- **`model.py`**: Implementation of the denoising diffusion model.
- **`sample.py`**: Code for generating protein backbone coordinates using the trained model.
- **`train.py`**: Handles the training process for the model.

---

For equations to render properly on GitHub, mathematical expressions are wrapped within **double-dollar signs** (`$$`) for block-level equations or single dollar signs (`$`) for inline equations. Use a Markdown renderer like **GitHub Pages** or **Jupyter Notebook** for better visualization of the equations.

---
