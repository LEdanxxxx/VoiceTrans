"""
flash_attn compatibility shim for Windows (uses PyTorch SDPA).
Replaces flash_attn_varlen_func with scaled_dot_product_attention.
"""
import torch
import torch.nn.functional as F

def flash_attn_varlen_func(
    q, k, v,
    cu_seqlens_q, cu_seqlens_k,
    max_seqlen_q, max_seqlen_k,
    dropout_p=0.0,
    softmax_scale=None,
    causal=False,
    window_size=(-1, -1),
    return_attn_probs=False,
    **kwargs
):
    """
    Variable-length flash attention using PyTorch SDPA.
    Adapts packed [total_tokens, heads, dim] format to padded for SDPA.
    """
    if softmax_scale is None:
        softmax_scale = 1.0 / (q.shape[-1] ** 0.5)

    total_tokens_q, num_heads, head_dim = q.shape
    total_tokens_k = k.shape[0]
    batch_size = cu_seqlens_q.shape[0] - 1

    seq_lens_q = (cu_seqlens_q[1:] - cu_seqlens_q[:-1]).tolist()
    seq_lens_k = (cu_seqlens_k[1:] - cu_seqlens_k[:-1]).tolist()

    max_len_q = int(max_seqlen_q.item())
    max_len_k = int(max_seqlen_k.item())

    # Use max of both for padded tensor size
    pad_len = max(max_len_q, max_len_k)

    q_padded = q.new_zeros(batch_size, num_heads, pad_len, head_dim)
    k_padded = k.new_zeros(batch_size, num_heads, pad_len, head_dim)
    v_padded = v.new_zeros(batch_size, num_heads, pad_len, head_dim)
    # key_padding_mask: True = ignore
    key_mask = torch.ones(batch_size, pad_len, dtype=torch.bool, device=q.device)

    for i in range(batch_size):
        s_q = cu_seqlens_q[i].item()
        e_q = cu_seqlens_q[i + 1].item()
        s_k = cu_seqlens_k[i].item()
        e_k = cu_seqlens_k[i + 1].item()
        len_q = e_q - s_q
        len_k = e_k - s_k

        q_padded[i, :, :len_q, :] = q[s_q:e_q].transpose(0, 1)
        k_padded[i, :, :len_k, :] = k[s_k:e_k].transpose(0, 1)
        v_padded[i, :, :len_k, :] = v[s_k:e_k].transpose(0, 1)
        key_mask[i, len_k:] = True  # mask k padding

    # q_padded already [batch, heads, pad_len, dim] - correct for SDPA

    # Build attention mask for SDPA
    # SDPA bool mask: True=attend, False=masked
    # key_mask: True for padded k positions
    # q positions to mask: [batch, pad_len]
    q_mask = torch.ones(batch_size, pad_len, dtype=torch.bool, device=q.device)
    for i, lq in enumerate(seq_lens_q):
        q_mask[i, :lq] = False
    # key positions to mask: [batch, 1, 1, pad_len]
    key_mask_expanded = (~key_mask).unsqueeze(1).unsqueeze(2)
    # query positions to mask: [batch, 1, pad_len, 1]
    q_mask_expanded = (~q_mask).unsqueeze(1).unsqueeze(-1)
    # Combined: [batch, 1, pad_len, pad_len]
    attn_mask = key_mask_expanded & q_mask_expanded

    is_causal = causal and window_size[0] <= 0

    out = F.scaled_dot_product_attention(
        q_padded, k_padded, v_padded,
        attn_mask=attn_mask,
        dropout_p=dropout_p,
        scale=softmax_scale,
        is_causal=is_causal,
    )
    # out: [batch, heads, pad_len, dim]
    # Unpack back to [total_tokens_q, heads, dim]
    result = q.new_zeros(total_tokens_q, num_heads, head_dim)
    for i in range(batch_size):
        start = cu_seqlens_q[i].item()
        end = cu_seqlens_q[i + 1].item()
        length = end - start
        result[start:end] = out[i, :, :length, :].transpose(0, 1)  # [heads,length,dim] -> [length,heads,dim]

    if return_attn_probs:
        return result, None
    return result


# Also provide the module-level attrs that might be accessed
__all__ = ['flash_attn_varlen_func']
