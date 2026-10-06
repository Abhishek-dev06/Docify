"""Small CPU-friendly U-Net; no pretrained or production accuracy claim."""

import torch
from torch import nn


def block(cin: int, cout: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(cin, cout, 3, padding=1),
        nn.ReLU(),
        nn.Conv2d(cout, cout, 3, padding=1),
        nn.ReLU(),
    )


class TinyUNet(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.enc1 = block(3, 8)
        self.enc2 = block(8, 16)
        self.bridge = block(16, 32)
        self.pool = nn.MaxPool2d(2)
        self.dec2 = block(48, 16)
        self.dec1 = block(24, 8)
        self.head = nn.Conv2d(8, 1, 1)

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        a = self.enc1(image)
        b = self.enc2(self.pool(a))
        c = self.bridge(self.pool(b))
        c = nn.functional.interpolate(
            c, size=b.shape[-2:], mode="bilinear", align_corners=False
        )
        b = self.dec2(torch.cat((b, c), 1))
        b = nn.functional.interpolate(
            b, size=a.shape[-2:], mode="bilinear", align_corners=False
        )
        return self.head(self.dec1(torch.cat((a, b), 1)))
