data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

data "aws_ssm_parameter" "ubuntu_ami" {
  name = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
}

# ---------- red ----------

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true

  tags = { Name = "prelo" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = false

  tags = { Name = "prelo-public" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "prelo" {
  name        = "prelo"
  description = "Prelo: 443 publico, SSH solo desde ssh_cidr"
  vpc_id      = aws_vpc.main.id
}

# Webhook de GitHub y POST /posts. Único puerto abierto a 0.0.0.0/0.
resource "aws_vpc_security_group_ingress_rule" "https" {
  security_group_id = aws_security_group.prelo.id
  description       = "HTTPS"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_ingress_rule" "ssh" {
  security_group_id = aws_security_group.prelo.id
  description       = "SSH desde IP fija"
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
  cidr_ipv4         = var.ssh_cidr
}

# Salida solo por 443: APIs de LLM, Slack, LinkedIn, GHCR, SSM y apt (user_data lo pasa a https).
resource "aws_vpc_security_group_egress_rule" "https" {
  security_group_id = aws_security_group.prelo.id
  description       = "Salida HTTPS"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

# ---------- permisos ----------

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "prelo" {
  name               = "prelo-ec2"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

# Permite el despliegue por SSM Run Command (F4.5).
resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.prelo.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "secrets" {
  statement {
    actions   = ["ssm:GetParametersByPath", "ssm:GetParameters", "ssm:GetParameter"]
    resources = ["arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter${var.ssm_prefix}/*"]
  }
}

resource "aws_iam_role_policy" "secrets" {
  name   = "prelo-secrets"
  role   = aws_iam_role.prelo.id
  policy = data.aws_iam_policy_document.secrets.json
}

resource "aws_iam_instance_profile" "prelo" {
  name = "prelo-ec2"
  role = aws_iam_role.prelo.name
}

# ---------- cómputo ----------

resource "aws_instance" "prelo" {
  ami                    = data.aws_ssm_parameter.ubuntu_ami.value
  instance_type          = var.instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.prelo.id]
  iam_instance_profile   = aws_iam_instance_profile.prelo.name
  key_name               = var.key_name

  metadata_options {
    http_tokens = "required"
  }

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    region     = var.region
    ssm_prefix = var.ssm_prefix
  })

  tags = { Name = "prelo" }
}

resource "aws_eip" "prelo" {
  domain   = "vpc"
  instance = aws_instance.prelo.id

  depends_on = [aws_internet_gateway.main]
}

# ---------- datos de Postgres ----------

resource "aws_ebs_volume" "data" {
  availability_zone = aws_subnet.public.availability_zone
  size              = var.data_volume_size
  type              = "gp3"
  encrypted         = true

  tags = {
    Name   = "prelo-postgres"
    Backup = "prelo-daily"
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_volume_attachment" "data" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.data.id
  instance_id = aws_instance.prelo.id
}

# ---------- backups diarios ----------

data "aws_iam_policy_document" "dlm_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["dlm.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "dlm" {
  name               = "prelo-dlm"
  assume_role_policy = data.aws_iam_policy_document.dlm_assume.json
}

resource "aws_iam_role_policy_attachment" "dlm" {
  role       = aws_iam_role.dlm.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSDataLifecycleManagerServiceRole"
}

resource "aws_dlm_lifecycle_policy" "daily" {
  description        = "Snapshots diarios del volumen de Postgres"
  execution_role_arn = aws_iam_role.dlm.arn
  state              = "ENABLED"

  policy_details {
    resource_types = ["VOLUME"]

    target_tags = {
      Backup = "prelo-daily"
    }

    schedule {
      name = "diario"

      create_rule {
        interval      = 24
        interval_unit = "HOURS"
        times         = ["05:00"]
      }

      retain_rule {
        count = var.snapshot_retention
      }

      copy_tags = true
    }
  }
}
