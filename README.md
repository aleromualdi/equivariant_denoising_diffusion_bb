# Denoising Diffusion with Equivariance for Protein Backbone Generation

This repository implements a **denoising diffusion probabilistic model (DDPM)** tailored to generate realistic protein backbone structures. The approach integrates **Equivariant Graph Neural Networks (EGNNs)**, ensuring robust handling of geometric transformations like rotation and translation. The repository is designed for ease of understanding, experimentation, and extension.


### **Data Representation**

Protein backbone structures are represented as Point clouds of atomic coordinates (`N`, `Cα`, `C`, `O`). Positional and mask arrays to identify known and missing atoms. Residue indices to encode the sequence position of amino acids.

Common data for protein backbone is the **CATH dataset** ([CATH: Protein Structure Classification](https://www.cathdb.info/)).

### **Model Architecture**

The model leverages **Equivariant Graph Neural Networks (EGNNs)** to ensure geometric consistency. 2Core components include:
- **Sinusoidal Positional Encoding**: Encodes residue indices and diffusion time steps for smooth learning.
- **EGNN Layers**: Update node and edge features while maintaining equivariance.
- **Directional Vectors for Equivariance**: 
  - **Directional Vectors**: The model explicitly computes and uses directional vectors $(\mathbf{x}_j - \mathbf{x}_i)$, where $\mathbf{x}_i$ and $\mathbf{x}_j$ are the coordinates of residues $i$ and $j$, respectively. These vectors inherently transform correctly under geometric transformations:
    - **Rotational Transformation**: When the entire protein structure is rotated, these directional vectors rotate accordingly, preserving their relative orientation.
    - **Translation Independence**: Translating the entire structure does not alter these vectors, as they are calculated relative to pairs of residues.
  - This design ensures that the message-passing and coordinate-update mechanisms in the EGNN layers remain equivariant, as all calculations are based on relative features rather than absolute positions.

By incorporating directional vectors as a foundation of the equivariant design, the model ensures that its predictions are robust to geometric transformations, which is essential for accurately modeling the spatially complex nature of protein backbones.

### **Code Organization**

- **`model.py`**: Contains the implementation of the denoising diffusion model.  
- **`sample.py`**: Includes the code for generating protein backbone coordinates using the trained model.  
- **`train.py`**: Handles the training process for the model.  
