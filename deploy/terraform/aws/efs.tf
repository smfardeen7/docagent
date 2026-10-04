# One encrypted file system, two access points (/data and /models), both
# owned by uid/gid 1000.
resource "aws_security_group" "efs" {
  name        = "${var.project}-efs"
  description = "NFS access from ECS tasks"
  vpc_id      = module.vpc.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "efs_from_tasks" {
  security_group_id            = aws_security_group.efs.id
  referenced_security_group_id = aws_security_group.tasks.id
  ip_protocol                  = "tcp"
  from_port                    = 2049
  to_port                      = 2049
}

resource "aws_efs_file_system" "this" {
  creation_token = "${var.project}-efs"
  encrypted      = true

  tags = {
    Name = "${var.project}-efs"
  }
}

resource "aws_efs_mount_target" "this" {
  count           = length(module.vpc.private_subnets)
  file_system_id  = aws_efs_file_system.this.id
  subnet_id       = module.vpc.private_subnets[count.index]
  security_groups = [aws_security_group.efs.id]
}

resource "aws_efs_access_point" "data" {
  file_system_id = aws_efs_file_system.this.id

  posix_user {
    uid = 1000
    gid = 1000
  }

  root_directory {
    path = "/data"
    creation_info {
      owner_uid   = 1000
      owner_gid   = 1000
      permissions = "0755"
    }
  }
}

resource "aws_efs_access_point" "models" {
  file_system_id = aws_efs_file_system.this.id

  posix_user {
    uid = 1000
    gid = 1000
  }

  root_directory {
    path = "/models"
    creation_info {
      owner_uid   = 1000
      owner_gid   = 1000
      permissions = "0755"
    }
  }
}
